from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.library.depends import get_metadata_resolver, get_pdf_fetcher
from app.pipelines.repo import RunRepository
from app.library.repo import PaperRepository, UserPaperRecord
from app.literature_support.scholar.identifiers import Identifier
from app.literature_support.scholar.metadata import MetadataResolver, ProviderMetadata
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
        from app.literature_support.scholar.pdf_fetch import DownloadedPdf

        self.urls.append(url)
        destination.write_bytes(self.payload)
        return DownloadedPdf(path=destination, byte_size=len(self.payload))


class FailingPdfFetcher:
    """Every source refuses, whatever URL an import offers."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def download(self, url: str, *, destination: Path):
        from app.platform.errors import AppError, ErrorCode

        self.urls.append(url)
        raise AppError(
            "来源没有提供可下载的 PDF",
            code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
            status_code=422,
        )


@pytest.fixture
def upload_paper(
    client: TestClient,
    api_prefix: str,
    db_session: Session,
    make_pdf,
    completed_imports,
) -> Callable[..., str]:
    """Upload a PDF and return the entry it becomes once the import finishes."""

    def _upload(
        token: str,
        *,
        pdf: bytes | None = None,
        filename: str = "paper.pdf",
    ) -> str:
        response = client.post(
            f"{api_prefix}/papers",
            headers=auth_headers(token),
            files={"file": (filename, pdf or make_pdf(), "application/pdf")},
        )
        assert response.status_code == 202, response.text
        db_session.expire_all()
        record = RunRepository(db_session).get(UUID(response.json()["run_id"]))
        assert record is not None and record.paper_id is not None
        entries = client.get(
            f"{api_prefix}/papers", headers=auth_headers(token)
        ).json()["items"]
        for entry in entries:
            user_paper = db_session.get(UserPaperRecord, UUID(entry["id"]))
            if user_paper is not None and user_paper.paper_id == record.paper_id:
                return str(entry["id"])
        raise AssertionError("upload produced no library entry")

    return _upload


def test_uploaded_pdf_is_the_paper_source_and_the_entry_only_links_it(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = upload_paper(token)

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    ).json()

    assert detail["capabilities"]["has_source"] is True
    assert detail["pdf"]["available"] is True
    assert detail["pdf"]["page_count"] == 1

    papers = PaperRepository(db_session).get_user_paper(UUID(paper_id))
    assert papers is not None and papers.paper_id is not None
    # The entry carries no bibliographic copy of its own.
    assert not hasattr(papers, "title")


def test_uploading_the_same_file_twice_shares_one_paper(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
    make_pdf,
    db_session: Session,
) -> None:
    owner = register_user(email="owner@example.com")["access_token"]
    stranger = register_user(email="stranger@example.com")["access_token"]
    pdf = make_pdf()

    owner_entry = upload_paper(owner, pdf=pdf)
    stranger_entry = upload_paper(stranger, pdf=pdf)

    owner_record = PaperRepository(db_session).get_user_paper(UUID(owner_entry))
    stranger_record = PaperRepository(db_session).get_user_paper(UUID(stranger_entry))
    assert owner_record is not None and stranger_record is not None
    assert owner_record.paper_id == stranger_record.paper_id
    assert owner_entry != stranger_entry


def test_pdf_download_is_revalidated_per_owner(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
) -> None:
    """The original file is cacheable per owner and unreadable to others."""
    owner = register_user(email="cache-owner@example.com")["access_token"]
    stranger = register_user(email="cache-stranger@example.com")["access_token"]
    paper_id = upload_paper(owner)
    url = f"{api_prefix}/papers/{paper_id}/pdf"

    downloaded = client.get(url, headers=auth_headers(owner))
    assert downloaded.status_code == 200
    etag = downloaded.headers["etag"]
    assert downloaded.headers["cache-control"] == "private, no-cache"

    cached = client.get(url, headers={**auth_headers(owner), "If-None-Match": etag})
    assert cached.status_code == 304
    assert cached.content == b""

    foreign = client.get(url, headers={**auth_headers(stranger), "If-None-Match": etag})
    assert foreign.status_code == 404


def test_a_different_file_is_a_different_paper(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
) -> None:
    from tests.conftest import build_pdf_with_text

    owner = register_user(email="cache-two@example.com")["access_token"]
    first = upload_paper(owner, pdf=build_pdf_with_text("First version"))
    second = upload_paper(owner, pdf=build_pdf_with_text("Another version"))

    assert first != second
    first_etag = client.get(
        f"{api_prefix}/papers/{first}/pdf", headers=auth_headers(owner)
    ).headers["etag"]
    second_etag = client.get(
        f"{api_prefix}/papers/{second}/pdf", headers=auth_headers(owner)
    ).headers["etag"]
    assert first_etag != second_etag


def test_the_pdf_replacement_entry_point_is_gone(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
    make_pdf,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = upload_paper(token)

    response = client.post(
        f"{api_prefix}/papers/{paper_id}/pdf",
        headers=auth_headers(token),
        files={"file": ("other.pdf", make_pdf(2), "application/pdf")},
    )

    assert response.status_code in {404, 405}


def test_user_cannot_edit_bibliographic_fields_when_the_endpoint_is_gone(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
) -> None:
    """Editing was removed so a single provider record stays authoritative."""
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = upload_paper(token)

    patched = client.patch(
        f"{api_prefix}/papers/{paper_id}/info",
        headers=auth_headers(token),
        json={"title": "Corrected Title", "year": 2019},
    )

    assert patched.status_code in {404, 405}


def test_user_cannot_trigger_a_metadata_lookup_when_the_endpoint_is_gone(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = upload_paper(token)

    response = client.post(
        f"{api_prefix}/papers/{paper_id}/fetch-metadata",
        headers=auth_headers(token),
    )

    assert response.status_code in {404, 405}


def test_pdf_operations_are_scoped_to_the_owner(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
) -> None:
    owner = register_user(email="owner-pdf@example.com")
    stranger = register_user(email="stranger-pdf@example.com")
    paper_id = upload_paper(owner["access_token"])

    response = client.get(
        f"{api_prefix}/papers/{paper_id}/pdf",
        headers=auth_headers(stranger["access_token"]),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "paper_not_found"


def test_metadata_resolution_fills_the_paper_from_a_single_provider(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
) -> None:
    """Ingestion writes the one bibliographic record the library reads."""
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = upload_paper(token)
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

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    ).json()

    assert detail["title"] is not None


def test_resolve_metadata_surfaces_provider_failure_without_crashing(
    client: TestClient,
    api_prefix: str,
    register_user,
    upload_paper: Callable[..., str],
) -> None:
    from app.platform.errors import AppError, ErrorCode

    token = register_user(email="reader@example.com")["access_token"]
    paper_id = upload_paper(token)
    provider = FakeProvider(
        error=AppError("down", code=ErrorCode.METADATA_PROVIDER_FAILED, status_code=502),
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider],
    )

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    )

    assert detail.status_code == 200
