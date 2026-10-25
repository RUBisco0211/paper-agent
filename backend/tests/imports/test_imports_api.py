from uuid import UUID

from fastapi.testclient import TestClient

from app.library.depends import get_metadata_resolver, get_pdf_fetcher
from app.library.repo import PaperRepository
from app.literature_support.scholar.metadata import MetadataResolver, ProviderMetadata
from app.platform.errors import AppError, ErrorCode
from tests.conftest import auth_headers
from tests.library.test_pdf_and_metadata import (
    FailingPdfFetcher,
    FakePdfFetcher,
    FakeProvider,
)

ARXIV_ID = "1706.03762"
ATTENTION = {
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer"],
    "abstract": "The dominant sequence transduction models are based on recurrence.",
    "arxiv_id": ARXIV_ID,
    "year": 2017,
}


def _import(client: TestClient, api_prefix: str, token: str, identifier: str, **extra):
    return client.post(
        f"{api_prefix}/imports",
        headers=auth_headers(token),
        json={"identifier": identifier, **extra},
    )


def test_arxiv_import_with_pdf_reaches_ready(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    completed_imports,
) -> None:
    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            pdf_url="https://example.org/1706.03762.pdf",
            **ATTENTION,
        ),
    )
    fetcher = FakePdfFetcher(make_pdf())
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: fetcher
    token = register_user(email="reader@example.com")["access_token"]

    response = _import(client, api_prefix, token, f"arXiv:{ARXIV_ID}v5")

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["identifier_type"] == "arxiv"
    assert body["identifier"] == ARXIV_ID
    assert body["paper_id"] is not None
    assert body["error_code"] is None
    assert body["finished_at"] is not None
    paper_id = body["paper_id"]
    UUID(paper_id)
    # The provider's link is tried first; arXiv's own path is only a fallback.
    assert fetcher.urls[0] == "https://example.org/1706.03762.pdf"

    detail = client.get(f"{api_prefix}/papers/{paper_id}", headers=auth_headers(token))
    assert detail.status_code == 200
    entry = detail.json()
    # Bibliographic facts arrive through the silent lookup, not the import, so
    # the import only guarantees the identifier and the stored file.
    assert entry["arxiv_id"] == ARXIV_ID
    assert entry["capabilities"]["has_source"] is True

    fetched_import = client.get(
        f"{api_prefix}/imports/{body['id']}",
        headers=auth_headers(token),
    )
    assert fetched_import.status_code == 200
    assert fetched_import.json()["status"] == "ready"

    pdf = client.get(f"{api_prefix}/papers/{paper_id}/pdf", headers=auth_headers(token))
    assert pdf.status_code == 200


def test_arxiv_doi_import_uses_arxiv_metadata_when_crossref_has_no_record(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    completed_imports,
) -> None:
    provider = FakeProvider(
        ProviderMetadata(
            source="arxiv",
            pdf_url="https://example.org/1706.03762.pdf",
            **ATTENTION,
        ),
    )
    provider.name = "arxiv"
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: FakePdfFetcher(make_pdf())
    token = register_user(email="arxiv-doi@example.com")["access_token"]

    response = _import(client, api_prefix, token, "10.48550/arXiv.1706.03762")

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "ready"
    assert response.json()["identifier_type"] == "arxiv"
    assert response.json()["identifier"] == ARXIV_ID
    assert response.json()["paper_id"] is not None
    items = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert items["total"] == 1
    assert items["items"][0]["arxiv_id"] == ARXIV_ID


def test_import_without_available_pdf_leaves_no_entry(
    client: TestClient,
    api_prefix: str,
    register_user,
    completed_imports,
) -> None:
    """An entry always points at a stored file, so a failed download adds none."""
    provider = FakeProvider(ProviderMetadata(source="fake", **ATTENTION))
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    # Every source refuses, including the arXiv path an identifier provides.
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: FailingPdfFetcher()
    token = register_user(email="reader@example.com")["access_token"]

    response = _import(client, api_prefix, token, ARXIV_ID)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "source_unavailable"
    assert body["error_code"] == "paper_pdf_not_available"
    assert body["paper_id"] is None

    library = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert library["total"] == 0


def test_repeat_import_reuses_the_same_entry(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    completed_imports,
) -> None:
    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            pdf_url="https://example.org/1706.03762.pdf",
            **ATTENTION,
        ),
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: FakePdfFetcher(
        make_pdf()
    )
    token = register_user(email="reader@example.com")["access_token"]

    first = _import(client, api_prefix, token, ARXIV_ID).json()
    second = _import(
        client, api_prefix, token, f"https://arxiv.org/abs/{ARXIV_ID}"
    ).json()

    assert first["paper_id"] == second["paper_id"]
    library = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert library["total"] == 1


def test_a_provider_outage_does_not_block_getting_the_source(
    client: TestClient,
    api_prefix: str,
    register_user,
    completed_imports,
) -> None:
    """Bibliographic lookup is best effort; the PDF comes from the identifier."""
    failing = FakeProvider(
        error=AppError(
            "元数据服务暂时不可用",
            code=ErrorCode.METADATA_PROVIDER_FAILED,
            status_code=502,
        ),
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [failing]
    )
    token = register_user(email="provider-down@example.com")["access_token"]

    response = _import(client, api_prefix, token, ARXIV_ID)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "ready"
    assert body["paper_id"] is not None
    items = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert items["total"] == 1


def test_an_identifier_with_no_source_leaves_nothing_behind(
    client: TestClient,
    api_prefix: str,
    register_user,
    completed_imports,
) -> None:
    """A DOI whose lookup and downloads all fail produces no library entry."""
    missing = FakeProvider(
        error=AppError(
            "没有查询到该标识符对应的论文",
            code=ErrorCode.METADATA_NOT_FOUND,
            status_code=404,
        ),
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [missing]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: FailingPdfFetcher()
    token = register_user(email="no-source@example.com")["access_token"]

    response = _import(client, api_prefix, token, "10.1234/does-not-exist")

    assert response.status_code == 202
    assert response.json()["status"] == "source_unavailable"
    assert (
        client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()["total"]
        == 0
    )


def test_import_rejects_unsupported_identifiers(
    client: TestClient,
    api_prefix: str,
    register_user,
    completed_imports,
) -> None:
    token = register_user(email="owner@example.com")["access_token"]

    invalid = _import(client, api_prefix, token, "attention is all you need")

    assert invalid.status_code == 422
    assert invalid.json()["code"] == "identifier_invalid"


def test_imports_are_isolated_between_users(
    client: TestClient,
    api_prefix: str,
    register_user,
    db_session,
    make_pdf,
    completed_imports,
) -> None:
    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            pdf_url="https://example.org/1706.03762.pdf",
            **ATTENTION,
        ),
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: FakePdfFetcher(
        make_pdf()
    )
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")

    created = _import(client, api_prefix, owner["access_token"], ARXIV_ID).json()

    foreign = client.get(
        f"{api_prefix}/imports/{created['id']}",
        headers=auth_headers(stranger["access_token"]),
    )
    assert foreign.status_code == 404
    assert foreign.json()["code"] == "import_not_found"

    owner_id = UUID(
        client.get(
            f"{api_prefix}/auth/me",
            headers=auth_headers(owner["access_token"]),
        ).json()["id"],
    )
    assert PaperRepository(db_session).find_user_paper_by_identifier(
        user_id=owner_id,
        arxiv_id=ARXIV_ID,
    )
