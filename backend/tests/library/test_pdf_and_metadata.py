from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.library.depends import get_metadata_resolver, get_pdf_fetcher
from app.library.domain import MetadataStatus, PaperSource
from app.library.repo import PaperRepository
from app.scholar.identifiers import Identifier
from app.scholar.metadata import MetadataResolver, ProviderMetadata
from tests.conftest import auth_headers


class FakeProvider:
    """Deterministic stand-in for Crossref/arXiv in API tests."""

    name = "fake"

    def __init__(
        self,
        metadata: ProviderMetadata | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.metadata = metadata
        self.error = error
        self.calls: list[Identifier] = []

    def supports(self, identifier: Identifier) -> bool:
        return True

    def fetch(self, identifier: Identifier) -> ProviderMetadata:
        self.calls.append(identifier)
        if self.error is not None:
            raise self.error
        assert self.metadata is not None
        return self.metadata


class FakePdfFetcher:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def download(self, url: str, *, destination: Path):
        from app.scholar.pdf_fetch import DownloadedPdf

        self.urls.append(url)
        destination.write_bytes(self.payload)
        return DownloadedPdf(path=destination, byte_size=len(self.payload))


@pytest.fixture
def create_entry(
    client: TestClient,
    api_prefix: str,
    db_session: Session,
) -> Callable[..., str]:
    """Create a metadata-only library entry directly, as an import would."""

    def _create(
        token: str,
        *,
        title: str = "Attention Is All You Need",
        doi: str | None = "10.5555/3295222.3295349",
        arxiv_id: str | None = None,
        source: PaperSource = PaperSource.DOI,
    ) -> str:
        user = client.get(
            f"{api_prefix}/auth/me",
            headers=auth_headers(token),
        ).json()
        user_paper = PaperRepository(db_session).add_user_paper(
            user_id=UUID(user["id"]),
            paper_id=None,
            title=title,
            source=source,
            doi=doi,
            arxiv_id=arxiv_id,
            metadata_status=MetadataStatus.UNRECOGNIZED,
        )
        db_session.commit()
        return str(user_paper.id)

    return _create


def test_attach_pdf_binds_entry_to_shared_paper(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    create_entry,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = create_entry(token)

    before = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    ).json()
    assert before["capabilities"]["has_pdf"] is False
    assert before["pdf"] == {"available": False, "page_count": None, "byte_size": None}

    attached = client.post(
        f"{api_prefix}/papers/{paper_id}/pdf",
        headers=auth_headers(token),
        files={"file": ("fulltext.pdf", make_pdf(), "application/pdf")},
    )

    assert attached.status_code == 202, attached.text
    body = attached.json()
    assert body["paper"]["id"] == paper_id
    assert body["paper"]["capabilities"]["has_pdf"] is True
    assert body["paper"]["doi"] == "10.5555/3295222.3295349"
    # Processing starts immediately; MinerU is not configured in tests.
    assert body["ingestion_job"]["status"] == "failed"
    assert body["ingestion_job"]["error_code"] == "provider_not_configured"

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    ).json()
    assert detail["pdf"]["available"] is True
    assert detail["pdf"]["page_count"] == 1

    downloaded = client.get(
        f"{api_prefix}/papers/{paper_id}/pdf",
        headers=auth_headers(token),
    )
    assert downloaded.status_code == 200


def test_pdf_cache_revalidates_when_the_file_changes(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    create_entry,
) -> None:
    owner = register_user(email="cache-owner@example.com")["access_token"]
    stranger = register_user(email="cache-stranger@example.com")["access_token"]
    paper_id = create_entry(owner, doi=None)
    url = f"{api_prefix}/papers/{paper_id}/pdf"
    first = client.post(
        url,
        headers=auth_headers(owner),
        files={"file": ("first.pdf", make_pdf(), "application/pdf")},
    )
    assert first.status_code == 202
    downloaded = client.get(url, headers=auth_headers(owner))
    assert downloaded.status_code == 200
    etag = downloaded.headers["etag"]
    assert downloaded.headers["cache-control"] == "private, no-cache"
    cached = client.get(url, headers={**auth_headers(owner), "If-None-Match": etag})
    assert cached.status_code == 304
    assert cached.content == b""
    assert client.get(url, headers={**auth_headers(stranger), "If-None-Match": etag}).status_code == 404

    from tests.conftest import build_pdf_with_text

    second = client.post(
        url,
        headers=auth_headers(owner),
        files={"file": ("second.pdf", build_pdf_with_text("Another version"), "application/pdf")},
    )
    assert second.status_code == 202
    changed = client.get(url, headers={**auth_headers(owner), "If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag


def test_attach_pdf_reports_identifier_conflict(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    create_entry,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = create_entry(token, doi="10.5555/1111111.2222222")
    from tests.conftest import build_pdf_with_text

    conflicting = build_pdf_with_text("See doi:10.1234/other-paper for details.")

    response = client.post(
        f"{api_prefix}/papers/{paper_id}/pdf",
        headers=auth_headers(token),
        files={"file": ("other.pdf", conflicting, "application/pdf")},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "metadata_conflict"
    assert response.json()["details"]["detected"] == "10.1234/other-paper"

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    ).json()
    assert detail["pdf"]["available"] is False
    assert detail["doi"] == "10.5555/1111111.2222222"


def test_edit_info_records_user_provenance(
    client: TestClient,
    api_prefix: str,
    register_user,
    create_entry,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = create_entry(token, title="placeholder", doi=None)

    patched = client.patch(
        f"{api_prefix}/papers/{paper_id}/info",
        headers=auth_headers(token),
        json={
            "title": "Corrected Title",
            "doi": "10.1145/3290605.3300233",
            "year": 2019,
        },
    )

    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["title"] == "Corrected Title"
    assert body["doi"] == "10.1145/3290605.3300233"
    assert body["year"] == 2019
    assert body["metadata_status"] == "user_provided"
    assert {(item["field"], item["source"]) for item in body["metadata_sources"]} == {
        ("title", "user"),
        ("doi", "user"),
        ("year", "user"),
    }


def test_edit_info_rejects_a_mismatched_identifier(
    client: TestClient,
    api_prefix: str,
    register_user,
    create_entry,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = create_entry(token)

    response = client.patch(
        f"{api_prefix}/papers/{paper_id}/info",
        headers=auth_headers(token),
        json={"arxiv_id": "10.1145/3290605.3300233"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "identifier_invalid"


def test_fetch_metadata_fills_missing_fields(
    client: TestClient,
    api_prefix: str,
    register_user,
    create_entry,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = create_entry(token, title=None, doi="10.1145/3290605.3300233")
    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            title="Learning to Rank",
            authors=["Ada Lovelace"],
            abstract="An abstract.",
            doi="10.1145/3290605.3300233",
            year=2019,
            venue="CHI",
        ),
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider],
    )

    response = client.post(
        f"{api_prefix}/papers/{paper_id}/fetch-metadata",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["metadata"]["status"] == "recognized"
    assert body["metadata"]["source"] == "fake"
    assert set(body["metadata"]["applied_fields"]) >= {"title", "authors", "abstract"}
    assert body["paper"]["title"] == "Learning to Rank"
    assert body["paper"]["authors"] == ["Ada Lovelace"]
    assert body["paper"]["venue"] == "CHI"
    assert provider.calls[0].value == "10.1145/3290605.3300233"


def test_fetch_metadata_does_not_overwrite_user_edits(
    client: TestClient,
    api_prefix: str,
    register_user,
    create_entry,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = create_entry(token, doi="10.1145/3290605.3300233")
    client.patch(
        f"{api_prefix}/papers/{paper_id}/info",
        headers=auth_headers(token),
        json={"title": "My Title", "authors": ["Me"]},
    )
    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            title="Provider Title",
            authors=["Someone Else"],
            doi="10.1145/3290605.3300233",
        ),
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider],
    )

    response = client.post(
        f"{api_prefix}/papers/{paper_id}/fetch-metadata",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["paper"]["title"] == "My Title"
    assert body["paper"]["authors"] == ["Me"]
    assert body["metadata"]["applied_fields"] == []


def test_resolve_metadata_surfaces_provider_failure_without_crashing(
    client: TestClient,
    api_prefix: str,
    register_user,
    create_entry,
) -> None:
    from app.platform.errors import AppError, ErrorCode

    token = register_user(email="reader@example.com")["access_token"]
    paper_id = create_entry(token)
    provider = FakeProvider(
        error=AppError(
            "元数据服务暂时不可用",
            code=ErrorCode.METADATA_PROVIDER_FAILED,
            status_code=502,
        ),
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider],
    )

    response = client.post(
        f"{api_prefix}/papers/{paper_id}/fetch-metadata",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["status"] == "provider_failed"
    assert body["metadata"]["error_code"] == "metadata_provider_failed"
    assert body["paper"]["title"] == "Attention Is All You Need"


def test_fetch_pdf_downloads_and_binds_when_source_offers_a_file(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    create_entry,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = create_entry(token, doi="10.1145/3290605.3300233")
    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            title="Learning to Rank",
            authors=["Ada Lovelace"],
            doi="10.1145/3290605.3300233",
            pdf_url="https://example.org/paper.pdf",
        ),
    )
    fetcher = FakePdfFetcher(make_pdf())
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider],
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: fetcher

    response = client.post(
        f"{api_prefix}/papers/{paper_id}/fetch-pdf",
        headers=auth_headers(token),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["paper"]["capabilities"]["has_pdf"] is True
    assert body["metadata"]["status"] == "recognized"
    assert fetcher.urls == ["https://example.org/paper.pdf"]

    downloaded = client.get(
        f"{api_prefix}/papers/{paper_id}/pdf",
        headers=auth_headers(token),
    )
    assert downloaded.status_code == 200


def test_fetch_pdf_reports_a_source_without_a_file(
    client: TestClient,
    api_prefix: str,
    register_user,
    create_entry,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = create_entry(token, doi="10.1145/3290605.3300233")
    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            title="Learning to Rank",
            authors=["Ada Lovelace"],
            doi="10.1145/3290605.3300233",
        ),
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider],
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: FakePdfFetcher(b"")

    response = client.post(
        f"{api_prefix}/papers/{paper_id}/fetch-pdf",
        headers=auth_headers(token),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "paper_pdf_not_available"

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    ).json()
    assert detail["pdf"]["available"] is False
    assert detail["title"] == "Learning to Rank"


def test_pdf_operations_are_scoped_to_the_owner(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    create_entry,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    paper_id = create_entry(owner["access_token"])

    attach = client.post(
        f"{api_prefix}/papers/{paper_id}/pdf",
        headers=auth_headers(stranger["access_token"]),
        files={"file": ("fulltext.pdf", make_pdf(), "application/pdf")},
    )
    patch = client.patch(
        f"{api_prefix}/papers/{paper_id}/info",
        headers=auth_headers(stranger["access_token"]),
        json={"title": "Stolen"},
    )
    resolve = client.post(
        f"{api_prefix}/papers/{paper_id}/fetch-metadata",
        headers=auth_headers(stranger["access_token"]),
    )

    for response in (attach, patch, resolve):
        assert response.status_code == 404
        assert response.json()["code"] == "paper_not_found"
