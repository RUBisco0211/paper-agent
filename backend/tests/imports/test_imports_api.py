from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.library.depends import get_metadata_resolver, get_pdf_fetcher
from app.library.repo import PaperRecord, PaperRepository
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


def _entry_paper_id(client: TestClient, api_prefix: str, token: str):
    """The paper behind the user's only library entry."""
    items = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert items["total"] == 1, items
    entry_id = items["items"][0]["id"]
    detail = client.get(
        f"{api_prefix}/papers/{entry_id}", headers=auth_headers(token)
    ).json()
    return detail.get("paper_id") or entry_id


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
    assert body["status"] == "success"
    assert body["identifier_type"] == "arxiv"
    assert body["identifier"] == ARXIV_ID
    paper_id = _entry_paper_id(client, api_prefix, token)
    UUID(str(paper_id))
    # The provider's link is tried first; arXiv's own path is only a fallback.
    assert fetcher.urls[0] == "https://example.org/1706.03762.pdf"

    detail = client.get(f"{api_prefix}/papers/{paper_id}", headers=auth_headers(token))
    assert detail.status_code == 200
    entry = detail.json()
    # Bibliographic facts arrive through the silent lookup, not the import, so
    # the import only guarantees the identifier and the stored file.
    assert entry["arxiv_id"] == ARXIV_ID
    assert entry["capabilities"]["has_source"] is True

    queue = client.get(
        f"{api_prefix}/imports/queue", headers=auth_headers(token)
    ).json()
    item = queue["items"][0]
    assert item["status"] == "success"
    assert item["run"]["status"] == "success"

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
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: FakePdfFetcher(
        make_pdf()
    )
    token = register_user(email="arxiv-doi@example.com")["access_token"]

    response = _import(client, api_prefix, token, "10.48550/arXiv.1706.03762")

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "success"
    assert response.json()["identifier_type"] == "arxiv"
    assert response.json()["identifier"] == ARXIV_ID
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
    assert response.json()["status"] == "failed"

    queue = client.get(
        f"{api_prefix}/imports/queue", headers=auth_headers(token)
    ).json()
    item = queue["items"][0]
    # The request keeps its failure and its reason; nothing was processed.
    assert item["status"] == "failed"
    assert item["error_message"] == "没有找到可用的原文"
    assert item["run"] is None

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

    # Two requests, one paper, one entry: the same file was stored once.
    assert first["status"] == "success" and second["status"] == "success"
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
    # The arXiv path is stable even when the lookup provider is down.
    assert response.json()["status"] == "success"
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
    assert response.json()["status"] == "failed"
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

    _import(client, api_prefix, owner["access_token"], ARXIV_ID)

    stranger_queue = client.get(
        f"{api_prefix}/imports/queue", headers=auth_headers(stranger["access_token"])
    ).json()
    assert stranger_queue["items"] == []

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


def test_a_paper_whose_parse_failed_stays_out_of_the_library(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    session_factory,
    storage,
) -> None:
    """A failed run grants no entry, and the failure stays on record."""
    from app.literature_support.embedding import build_embedding_adapter
    from app.literature_support.importing.mineru import MineruParser
    from app.literature_support.scholar.metadata import ProviderMetadata
    from app.pipelines.pipeline import RunPipeline
    from app.pipelines.repo import RunRecord
    from app.platform.tasks import InlineTaskScheduler

    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            pdf_url="https://example.org/1706.03762.pdf",
            **ATTENTION,
        )
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: FakePdfFetcher(
        make_pdf()
    )
    token = register_user(email="reimport@example.com")["access_token"]

    _import(client, api_prefix, token, ARXIV_ID)
    # Drive the download that the request only recorded.
    from app.imports.depends import get_pdf_locator
    from app.pipelines.download import DownloadService

    downloads = DownloadService(
        session_factory=session_factory,
        storage=storage,
        fetcher=FakePdfFetcher(make_pdf()),
        resolver=MetadataResolver([provider]),
        locator=get_pdf_locator(),
    )
    while (download_id := downloads.claim_next()) is not None:
        downloads.run(download_id)

    # MinerU is unconfigured, so this run can only fail.
    RunPipeline(
        scheduler=InlineTaskScheduler(),
        session_factory=session_factory,
        storage=storage,
        mineru=MineruParser(base_url=None, api_key=None, timeout_seconds=30),
        embeddings=build_embedding_adapter(),
    ).run_sync(
        db_session.scalars(select(RunRecord).order_by(RunRecord.created_at)).first().id
    )

    library = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert library["total"] == 0
    queue = client.get(
        f"{api_prefix}/imports/queue", headers=auth_headers(token)
    ).json()
    assert queue["items"][0]["run"]["status"] == "failed"
    assert queue["items"][0]["run"]["error_message"] is not None


def test_a_second_user_importing_the_same_paper_gets_their_own_entry(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    completed_imports,
) -> None:
    """Two people asking for the same paper share the work, not the entry."""
    from app.library.repo import PaperRepository
    from app.pipelines.repo import DownloadRecord, RunRecord

    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            pdf_url="https://example.org/1706.03762.pdf",
            **ATTENTION,
        )
    )
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: FakePdfFetcher(
        make_pdf()
    )
    first = register_user(email="first-waiter@example.com")
    second = register_user(email="second-waiter@example.com")

    first_result = _import(client, api_prefix, first["access_token"], ARXIV_ID)
    assert first_result.status_code == 202, first_result.text
    second_result = _import(client, api_prefix, second["access_token"], ARXIV_ID)
    assert second_result.status_code == 202, second_result.text

    db_session.expire_all()
    assert db_session.scalar(select(func.count(PaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(DownloadRecord.id))) == 2
    # The same file was processed once, no matter how many people asked.
    assert db_session.scalar(select(func.count(RunRecord.id))) == 1

    papers = PaperRepository(db_session)
    for account in (first, second):
        user_id = UUID(
            client.get(
                f"{api_prefix}/auth/me", headers=auth_headers(account["access_token"])
            ).json()["id"]
        )
        library = client.get(
            f"{api_prefix}/papers", headers=auth_headers(account["access_token"])
        ).json()
        assert library["total"] == 1, "every importer keeps their own entry"
        assert papers.find_user_paper_by_identifier(
            user_id=user_id, arxiv_id=ARXIV_ID
        ) is not None
