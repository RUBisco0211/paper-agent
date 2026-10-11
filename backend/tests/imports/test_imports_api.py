from uuid import UUID

from fastapi.testclient import TestClient

from app.library.depends import get_metadata_resolver, get_pdf_fetcher
from app.library.repo import PaperRepository
from app.literature_support.scholar.metadata import MetadataResolver, ProviderMetadata
from app.platform.errors import AppError, ErrorCode
from tests.conftest import auth_headers
from tests.library.test_pdf_and_metadata import FakePdfFetcher, FakeProvider

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
    assert body["metadata_source"] == "fake"
    assert body["error_code"] is None
    assert body["finished_at"] is not None
    paper_id = body["paper_id"]
    UUID(paper_id)
    assert fetcher.urls == ["https://example.org/1706.03762.pdf"]

    detail = client.get(f"{api_prefix}/papers/{paper_id}", headers=auth_headers(token))
    assert detail.status_code == 200
    entry = detail.json()
    assert entry["title"] == ATTENTION["title"]
    assert entry["authors"] == ATTENTION["authors"]
    assert entry["arxiv_id"] == ARXIV_ID
    assert entry["metadata_status"] == "recognized"
    assert entry["capabilities"]["has_pdf"] is True

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
    assert response.json()["metadata_source"] == "arxiv"


def test_import_without_available_pdf_keeps_the_entry(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    provider = FakeProvider(ProviderMetadata(source="fake", **ATTENTION))
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    token = register_user(email="reader@example.com")["access_token"]

    response = _import(client, api_prefix, token, ARXIV_ID)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "pdf_unavailable"
    assert body["error_code"] == "paper_pdf_not_available"

    entry = client.get(
        f"{api_prefix}/papers/{body['paper_id']}",
        headers=auth_headers(token),
    ).json()
    assert entry["title"] == ATTENTION["title"]
    assert entry["capabilities"]["has_pdf"] is False
    assert entry["pdf"] == {"available": False, "page_count": None, "byte_size": None}

    library = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert library["total"] == 1
    assert library["items"][0]["processing"]["status"] is None


def test_import_can_add_the_entry_to_a_project(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    provider = FakeProvider(ProviderMetadata(source="fake", **ATTENTION))
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    token = register_user(email="reader@example.com")["access_token"]
    project = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(token),
        json={"name": "Reading"},
    ).json()

    response = _import(client, api_prefix, token, ARXIV_ID, project_id=project["id"])

    assert response.status_code == 202, response.text
    assert response.json()["project_id"] == project["id"]
    members = client.get(
        f"{api_prefix}/projects/{project['id']}/papers",
        headers=auth_headers(token),
    ).json()
    assert members["total"] == 1
    assert members["items"][0]["id"] == response.json()["paper_id"]


def test_repeat_import_reuses_the_same_entry(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    provider = FakeProvider(ProviderMetadata(source="fake", **ATTENTION))
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    token = register_user(email="reader@example.com")["access_token"]

    first = _import(client, api_prefix, token, ARXIV_ID).json()
    second = _import(
        client, api_prefix, token, f"https://arxiv.org/abs/{ARXIV_ID}"
    ).json()

    assert first["paper_id"] == second["paper_id"]
    library = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert library["total"] == 1


def test_import_reports_provider_and_lookup_failures_differently(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
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
    token = register_user(email="reader@example.com")["access_token"]

    provider_down = _import(client, api_prefix, token, ARXIV_ID)
    assert provider_down.status_code == 202
    assert provider_down.json()["status"] == "failed"
    assert provider_down.json()["error_code"] == "metadata_provider_failed"
    assert provider_down.json()["paper_id"] is None

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
    not_found = _import(client, api_prefix, token, "10.1234/does-not-exist")

    assert not_found.status_code == 202
    assert not_found.json()["status"] == "failed"
    assert not_found.json()["error_code"] == "metadata_not_found"
    assert (
        client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()["total"]
        == 0
    )


def test_import_rejects_unsupported_identifiers_and_foreign_projects(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    token = owner["access_token"]

    invalid = _import(client, api_prefix, token, "attention is all you need")
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "identifier_invalid"

    project = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(token),
        json={"name": "Mine"},
    ).json()
    foreign = _import(
        client,
        api_prefix,
        stranger["access_token"],
        ARXIV_ID,
        project_id=project["id"],
    )
    assert foreign.status_code == 404
    assert foreign.json()["code"] == "project_not_found"


def test_imports_are_isolated_between_users(
    client: TestClient,
    api_prefix: str,
    register_user,
    db_session,
) -> None:
    provider = FakeProvider(ProviderMetadata(source="fake", **ATTENTION))
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
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
