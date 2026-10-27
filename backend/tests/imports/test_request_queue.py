"""A request remembers where it should land, and the queue shows both doors."""


from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.library.depends import get_metadata_resolver, get_pdf_fetcher
from app.literature_support.scholar.metadata import MetadataResolver, ProviderMetadata
from app.pipelines.repo import RunRecord, UserRunRecord
from tests.conftest import auth_headers
from tests.imports.test_imports_api import ARXIV_ID, ATTENTION
from tests.library.test_pdf_and_metadata import FakePdfFetcher, FakeProvider


def _create_project(client: TestClient, api_prefix: str, token: str, name: str) -> str:
    response = client.post(
        f"{api_prefix}/projects", headers=auth_headers(token), json={"name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload(
    client: TestClient, api_prefix: str, token: str, pdf: bytes, **form
):
    return client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("paper.pdf", pdf, "application/pdf")},
        data=form or None,
    )


def _queue(client: TestClient, api_prefix: str, token: str) -> list[dict]:
    response = client.get(f"{api_prefix}/imports/queue", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_an_upload_appears_in_the_queue_without_any_download(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    completed_imports,
) -> None:
    """An upload has no download row, so the request itself must show up."""
    token = register_user(email="upload-queue@example.com")["access_token"]

    assert _upload(client, api_prefix, token, make_pdf()).status_code == 202

    items = _queue(client, api_prefix, token)
    assert len(items) == 1
    assert items[0]["source"] == "request"
    assert items[0]["status"] == "success"


def test_a_download_and_its_request_show_up_once(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    completed_imports,
) -> None:
    """The download already speaks for its run, so the request stays hidden."""
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
    token = register_user(email="dedupe@example.com")["access_token"]

    response = client.post(
        f"{api_prefix}/imports",
        headers=auth_headers(token),
        json={"identifier": ARXIV_ID},
    )
    assert response.status_code == 202, response.text

    items = _queue(client, api_prefix, token)
    assert len(items) == 1, items
    assert items[0]["source"] == "download"
    assert items[0]["status"] == "success"


def test_an_upload_into_a_project_files_the_entry_when_it_finishes(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    completed_imports,
) -> None:
    token = register_user(email="project-upload@example.com")["access_token"]
    project_id = _create_project(client, api_prefix, token, "Reading")

    response = _upload(
        client, api_prefix, token, make_pdf(), project_id=project_id
    )
    assert response.status_code == 202, response.text

    papers = client.get(
        f"{api_prefix}/projects/{project_id}/papers", headers=auth_headers(token)
    )
    assert papers.status_code == 200, papers.text
    assert papers.json()["total"] == 1
    # The request remembers the project it asked for.
    with db_session as session:
        stored = session.scalars(select(UserRunRecord)).first()
        assert stored is not None
        assert str(stored.project_id) == project_id


def test_an_import_naming_someone_elses_project_is_refused_immediately(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    completed_imports,
) -> None:
    owner = register_user(email="project-owner@example.com")["access_token"]
    other = register_user(email="project-other@example.com")["access_token"]
    project_id = _create_project(client, api_prefix, owner, "Mine")

    response = client.post(
        f"{api_prefix}/imports",
        headers=auth_headers(other),
        json={"identifier": ARXIV_ID, "project_id": project_id},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "project_not_found"
    # Nothing was queued for a request that could never succeed.
    assert _queue(client, api_prefix, other) == []


def test_uploading_an_already_usable_paper_grants_it_without_queueing(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    completed_imports,
) -> None:
    """Nothing is left to watch, so the paper just lands in the library."""
    token = register_user(email="again@example.com")["access_token"]
    project_id = _create_project(client, api_prefix, token, "Second")

    first = _upload(client, api_prefix, token, make_pdf())
    assert first.status_code == 202
    second = _upload(
        client, api_prefix, token, make_pdf(), project_id=project_id
    )
    assert second.status_code == 202

    # One queue row: the request that actually needed processing.
    items = _queue(client, api_prefix, token)
    assert len(items) == 1, items
    assert items[0]["source"] == "request"
    # The second upload still did what it promised: filed the paper.
    papers = client.get(
        f"{api_prefix}/projects/{project_id}/papers", headers=auth_headers(token)
    )
    assert papers.json()["total"] == 1
    # No second run, and no request row for work nobody had to do.
    with db_session as session:
        assert len(session.scalars(select(RunRecord)).all()) == 1
        assert len(session.scalars(select(UserRunRecord)).all()) == 1


def test_importing_a_stored_identifier_does_not_download_again(
    client, api_prefix, register_user, make_pdf, db_session, completed_imports
):
    """A paper already in the library is joined, never fetched a second time."""
    from app.library.depends import get_metadata_resolver, get_pdf_fetcher
    from app.library.repo import PaperRecord
    from app.literature_support.scholar.metadata import (
        MetadataResolver,
        ProviderMetadata,
    )
    from app.pipelines.repo import DownloadRecord, RunRecord
    from tests.imports.test_imports_api import ARXIV_ID, ATTENTION
    from tests.library.test_pdf_and_metadata import FakePdfFetcher, FakeProvider

    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            pdf_url="https://example.org/1706.03762.pdf",
            **ATTENTION,
        )
    )
    fetcher = FakePdfFetcher(make_pdf())
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: fetcher
    token = register_user(email="reuse@example.com")["access_token"]

    first = client.post(
        f"{api_prefix}/imports",
        headers=auth_headers(token),
        json={"identifier": ARXIV_ID},
    )
    assert first.status_code == 202, first.text
    downloads_after_first = db_session.query(DownloadRecord).count()
    assert downloads_after_first == 1

    second = client.post(
        f"{api_prefix}/imports",
        headers=auth_headers(token),
        json={"identifier": ARXIV_ID},
    )
    assert second.status_code == 202, second.text

    db_session.expire_all()
    # No second fetch, because the file was already stored.
    assert db_session.query(DownloadRecord).count() == downloads_after_first
    assert db_session.query(PaperRecord).count() == 1
    assert db_session.query(RunRecord).count() == 1


def test_a_paper_row_without_its_file_is_downloaded_again(
    client, api_prefix, register_user, make_pdf, db_session, completed_imports, storage
):
    """A leftover row must not stand in for a missing file."""
    from app.library.depends import get_metadata_resolver, get_pdf_fetcher
    from app.library.repo import PaperRecord
    from app.literature_support.scholar.metadata import (
        MetadataResolver,
        ProviderMetadata,
    )
    from app.pipelines.repo import DownloadRecord
    from app.platform.storage import paper_pdf_key
    from tests.imports.test_imports_api import ARXIV_ID, ATTENTION
    from tests.library.test_pdf_and_metadata import FakePdfFetcher, FakeProvider

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
    token = register_user(email="missing-file@example.com")["access_token"]

    first = client.post(
        f"{api_prefix}/imports",
        headers=auth_headers(token),
        json={"identifier": ARXIV_ID},
    )
    assert first.status_code == 202, first.text
    with db_session as session:
        paper = session.query(PaperRecord).one()
        stored_hash = paper.file_hash
    storage.delete(paper_pdf_key(stored_hash))

    second = client.post(
        f"{api_prefix}/imports",
        headers=auth_headers(token),
        json={"identifier": ARXIV_ID},
    )
    assert second.status_code == 202, second.text

    db_session.expire_all()
    # The row was there but the file was not, so a fresh download was queued.
    assert db_session.query(DownloadRecord).count() == 2
