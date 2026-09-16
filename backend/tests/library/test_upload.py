from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.application import IngestionService
from app.ingestion.persistence import (
    IngestionJobRecord,
    IngestionRepository,
    IngestionStageRecordOrm,
)
from app.library.application import PaperLibraryService
from app.library.dependencies import get_paper_library_service
from app.library.persistence import PaperRecord, PaperRepository, UserPaperRecord
from app.platform.storage import LocalObjectStorage
from tests.conftest import auth_headers

PDF_FILENAME = "attention is all you need.pdf"


def _upload(
    client: TestClient,
    api_prefix: str,
    token: str,
    pdf: bytes,
    *,
    filename: str = PDF_FILENAME,
):
    return client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": (filename, pdf, "application/pdf")},
    )


def test_upload_creates_entry_and_ingestion_job(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    response = _upload(client, api_prefix, token, make_pdf())

    assert response.status_code == 202, response.text
    body = response.json()
    paper = body["paper"]
    UUID(paper["id"])
    assert paper["title"] == "attention is all you need"
    assert paper["original_filename"] == PDF_FILENAME
    assert paper["source"] == "upload"
    assert paper["capabilities"] == {
        "has_pdf": True,
        "has_metadata": False,
        "has_fulltext": False,
        "has_keyword_index": False,
        "has_embedding": False,
    }
    assert paper["processing"]["status"] == "queued"

    job = body["ingestion_job"]
    assert job["paper_id"] == paper["id"]
    assert job["status"] == "queued"
    assert {stage["stage"] for stage in job["stages"]} == {
        "metadata",
        "fulltext",
        "chunking",
        "embedding",
    }
    assert {stage["status"] for stage in job["stages"]} == {"pending"}

    assert db_session.scalar(select(func.count(PaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(UserPaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(IngestionJobRecord.id))) == 1
    assert db_session.scalar(select(func.count(IngestionStageRecordOrm.id))) == 4


def test_duplicate_upload_reuses_entry_and_job(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    pdf = make_pdf()

    first = _upload(client, api_prefix, token, pdf)
    second = _upload(client, api_prefix, token, pdf, filename="renamed.pdf")

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["paper"]["id"] == second.json()["paper"]["id"]
    # The reuse path returns the still-active job instead of stacking a new one.
    assert first.json()["ingestion_job"]["id"] == second.json()["ingestion_job"]["id"]
    assert db_session.scalar(select(func.count(PaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(UserPaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(IngestionJobRecord.id))) == 1


def test_two_users_sharing_a_pdf_stay_isolated(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    first_user = register_user(email="first@example.com")
    second_user = register_user(email="second@example.com")
    pdf = make_pdf()

    first = _upload(client, api_prefix, first_user["access_token"], pdf)
    second = _upload(client, api_prefix, second_user["access_token"], pdf)

    first_paper_id = first.json()["paper"]["id"]
    second_paper_id = second.json()["paper"]["id"]
    assert first_paper_id != second_paper_id
    # One shared PDF fact, two independent user entries.
    assert db_session.scalar(select(func.count(PaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(UserPaperRecord.id))) == 2

    foreign_detail = client.get(
        f"{api_prefix}/papers/{first_paper_id}",
        headers=auth_headers(second_user["access_token"]),
    )
    foreign_pdf = client.get(
        f"{api_prefix}/papers/{first_paper_id}/pdf",
        headers=auth_headers(second_user["access_token"]),
    )
    assert foreign_detail.status_code == 404
    assert foreign_detail.json()["code"] == "paper_not_found"
    assert foreign_pdf.status_code == 404


def test_upload_rejects_invalid_and_unreadable_files(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    not_pdf = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("notes.txt", b"just some text", "text/plain")},
    )
    assert not_pdf.status_code == 415
    assert not_pdf.json()["code"] == "pdf_invalid"

    truncated = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("broken.pdf", b"%PDF-1.7\nbroken", "application/pdf")},
    )
    assert truncated.status_code == 422
    assert truncated.json()["code"] == "pdf_unreadable"


def test_upload_enforces_size_and_page_limits(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    session_factory: sessionmaker[Session],
    storage_root: Path,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    def build_service(
        *,
        max_pdf_bytes: int | None = None,
        max_pdf_pages: int | None = None,
    ) -> Callable[[], Iterator[PaperLibraryService]]:
        def _build() -> Iterator[PaperLibraryService]:
            session = session_factory()
            try:
                papers = PaperRepository(session)
                yield PaperLibraryService(
                    papers,
                    IngestionService(IngestionRepository(session), papers),
                    LocalObjectStorage(storage_root),
                    max_pdf_bytes=max_pdf_bytes,
                    max_pdf_pages=max_pdf_pages,
                )
            finally:
                session.close()

        return _build

    oversized_pdf = make_pdf(page_count=3)
    client.app.dependency_overrides[get_paper_library_service] = build_service(
        max_pdf_bytes=len(oversized_pdf) - 1,
        max_pdf_pages=2,
    )
    oversized = _upload(client, api_prefix, token, oversized_pdf)
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "pdf_too_large"

    client.app.dependency_overrides[get_paper_library_service] = build_service(
        max_pdf_pages=2,
    )
    too_many_pages = _upload(client, api_prefix, token, make_pdf(page_count=3))
    assert too_many_pages.status_code == 422
    assert too_many_pages.json()["code"] == "pdf_too_many_pages"

    within_limits = _upload(client, api_prefix, token, make_pdf(page_count=2))
    assert within_limits.status_code == 202
