import hashlib
import json
from collections.abc import Callable, Iterator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.library.depends import (
    get_paper_library_service,
)
from app.library.repo import PaperRecord, PaperRepository, UserPaperRecord
from app.library.service import PaperLibraryService
from app.literature_support.scholar.enrichment import MetadataEnricher
from app.literature_support.scholar.metadata import build_default_resolver
from app.pipelines.domain import RunStage, RunStatus
from app.pipelines.repo import RunRecord, RunRepository
from app.platform.storage import ObjectStorage, mineru_artifact_key
from app.platform.tasks import InlineTaskScheduler
from tests.conftest import auth_headers

PDF_FILENAME = "attention is all you need.pdf"


def test_paper_detail_exposes_versions_when_owner_reads_quoted_sources(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    completed_imports,
) -> None:
    owner = register_user(email="quote-version-owner@example.com")
    stranger = register_user(email="quote-version-stranger@example.com")
    entry_id = _entry_id(client, api_prefix, owner["access_token"], make_pdf())
    paper = _paper_of(db_session, entry_id)

    detail = client.get(f"{api_prefix}/papers/{entry_id}", headers=auth_headers(owner["access_token"]))
    assert detail.status_code == 200
    assert detail.json()["pdf_version"] == paper.file_hash
    assert detail.json()["artifact_version"]
    assert client.get(f"{api_prefix}/papers/{entry_id}", headers=auth_headers(stranger["access_token"])).status_code == 404


def test_paper_blocks_are_filtered_and_private(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    storage: ObjectStorage,
    completed_imports,
) -> None:
    owner = register_user(email="block-owner@example.com")
    stranger = register_user(email="block-stranger@example.com")
    entry_id = _entry_id(client, api_prefix, owner["access_token"], make_pdf())
    paper = _paper_of(db_session, entry_id)
    index = {
        "types": ["text", "table"],
        "items": [
            {
                "id": 0,
                "type": "text",
                "page": 1,
                "text": "Body",
                "bbox": [10, 20, 100, 80],
                "page_size": [612, 792],
            },
            {
                "id": 1,
                "type": "table",
                "page": 2,
                "text": "Result",
                "bbox": None,
                "page_size": None,
            },
        ],
    }
    key = mineru_artifact_key(paper.file_hash, "blocks_index.json")
    payload = json.dumps(index).encode()
    storage.put_bytes(key, payload)
    content_key = mineru_artifact_key(paper.file_hash, "content_list.json")
    content_payload = json.dumps(
        [
            {"type": "text", "text": "Body", "page_idx": 0},
            {"type": "table", "table_body": "Result", "page_idx": 1},
            {
                "type": "image",
                "img_path": "images/figure-1.png",
                "img_caption": ["Figure 1"],
                "page_idx": 1,
            },
            {
                "type": "equation",
                "text": r"E = mc^2",
                "text_format": "latex",
                "page_idx": 1,
            },
        ]
    ).encode()
    storage.put_bytes(content_key, content_payload)
    image_key = mineru_artifact_key(paper.file_hash, "images/figure-1.png")
    image_payload = b"\x89PNG\r\n\x1a\npreview"
    storage.put_bytes(image_key, image_payload)
    manifest_key = mineru_artifact_key(paper.file_hash, "manifest.json")
    storage.put_bytes(
        manifest_key,
        json.dumps(
            {
                "file_hash": paper.file_hash,
                "files": {
                    "blocks_index.json": {
                        "key": key,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    },
                    "content_list.json": {
                        "key": content_key,
                        "sha256": hashlib.sha256(content_payload).hexdigest(),
                    },
                    "images/figure-1.png": {
                        "key": image_key,
                        "sha256": hashlib.sha256(image_payload).hexdigest(),
                    },
                },
            }
        ).encode(),
    )
    paper.artifact_manifest_key = manifest_key
    paper.has_parsed = True
    db_session.commit()

    response = client.get(
        f"{api_prefix}/papers/{entry_id}/blocks",
        params={"type": "table"},
        headers=auth_headers(owner["access_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["types"] == ["text", "table", "image", "equation"]
    assert [item["id"] for item in response.json()["items"]] == [1]
    blocks_url = f"{api_prefix}/papers/{entry_id}/blocks"
    assert client.get(
        blocks_url,
        params={"type": "table"},
        headers={**auth_headers(owner["access_token"]), "If-None-Match": response.headers["etag"]},
    ).status_code == 304
    assert client.get(
        blocks_url,
        params={"type": "text"},
        headers={**auth_headers(owner["access_token"]), "If-None-Match": response.headers["etag"]},
    ).status_code == 200
    assert client.get(
        blocks_url,
        params={"type": "table"},
        headers={**auth_headers(stranger["access_token"]), "If-None-Match": response.headers["etag"]},
    ).status_code == 404
    direct = client.get(
        f"{api_prefix}/papers/{entry_id}/blocks/1",
        headers=auth_headers(owner["access_token"]),
    )
    assert direct.status_code == 200
    assert direct.json()["page"] == 2
    assert client.get(
        f"{api_prefix}/papers/{entry_id}/blocks/1",
        headers={**auth_headers(owner["access_token"]), "If-None-Match": direct.headers["etag"]},
    ).status_code == 304
    image_block = client.get(
        f"{api_prefix}/papers/{entry_id}/blocks/2",
        headers=auth_headers(owner["access_token"]),
    )
    assert image_block.json()["has_image"] is True
    image = client.get(
        f"{api_prefix}/papers/{entry_id}/blocks/2/image",
        headers=auth_headers(owner["access_token"]),
    )
    assert image.status_code == 200
    assert image.content == image_payload
    assert image.headers["content-type"] == "image/png"
    assert (
        client.get(
            f"{api_prefix}/papers/{entry_id}/blocks/2/image",
            headers=auth_headers(stranger["access_token"]),
        ).status_code
        == 404
    )
    storage.put_bytes(image_key, b"tampered")
    assert (
        client.get(
            f"{api_prefix}/papers/{entry_id}/blocks/2/image",
            headers=auth_headers(owner["access_token"]),
        ).status_code
        == 502
    )
    assert (
        client.get(
            f"{api_prefix}/papers/{entry_id}/blocks/1",
            headers=auth_headers(stranger["access_token"]),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{api_prefix}/papers/{entry_id}/blocks",
            headers=auth_headers(stranger["access_token"]),
        ).status_code
        == 404
    )


def _entry_id(client: TestClient, api_prefix: str, token: str, pdf: bytes) -> UUID:
    """Upload a file and return the library entry it becomes."""
    response = _upload(client, api_prefix, token, pdf)
    assert response.status_code == 202, response.text
    items = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()[
        "items"
    ]
    return UUID(items[0]["id"])


def _paper_of(session: Session, entry_id: UUID) -> PaperRecord:
    entry = session.get(UserPaperRecord, entry_id)
    assert entry is not None and entry.paper_id is not None
    paper = session.get(PaperRecord, entry.paper_id)
    assert paper is not None
    return paper


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


def test_a_failed_upload_leaves_no_entry_in_the_library(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
) -> None:
    """Without a working parser the paper exists but nobody owns it yet."""
    token = register_user(email="reader@example.com")["access_token"]

    response = _upload(client, api_prefix, token, make_pdf())

    assert response.status_code == 202, response.text
    body = response.json()
    # The request only records the run; Failing here would need a worker.
    assert body["status"] == RunStatus.PENDING.value

    from app.literature_support.embedding import build_embedding_adapter
    from app.literature_support.importing.mineru import MineruParser
    from app.pipelines.pipeline import RunPipeline

    RunPipeline(
        scheduler=InlineTaskScheduler(),
        session_factory=session_factory,
        storage=storage,
        mineru=MineruParser(
            base_url=None, api_key=None, timeout_seconds=30
        ),
        embeddings=build_embedding_adapter(),
    ).run_sync(UUID(body["run_id"]))

    run = RunRepository(db_session).get(UUID(body["run_id"]))
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert run.current_stage is RunStage.PARSE
    assert run.error_message is not None

    # The paper and its file exist; the entry does not, because no run succeeded.
    assert db_session.scalar(select(func.count(PaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(UserPaperRecord.id))) == 0
    library = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert library["total"] == 0


def test_a_finished_upload_appears_in_the_library(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    completed_imports,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    response = _upload(client, api_prefix, token, make_pdf())

    assert response.status_code == 202, response.text
    run = RunRepository(db_session).get(UUID(response.json()["run_id"]))
    assert run is not None and run.status is RunStatus.SUCCESS
    assert run.current_stage is None

    library = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert library["total"] == 1
    assert library["items"][0]["capabilities"]["has_parsed"] is True


def test_a_second_upload_of_the_same_file_reuses_the_paper(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    completed_imports,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    pdf = make_pdf()

    first = _upload(client, api_prefix, token, pdf)
    second = _upload(client, api_prefix, token, pdf, filename="renamed.pdf")

    assert first.status_code == 202
    assert second.status_code == 202
    # One paper and one entry: the second upload changes nothing.
    assert db_session.scalar(select(func.count(PaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(UserPaperRecord.id))) == 1
    # The finished run was not repeated just because a file was uploaded again.
    assert db_session.scalar(select(func.count(RunRecord.id))) == 1


def test_two_users_sharing_a_pdf_stay_isolated(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    completed_imports,
) -> None:
    first_user = register_user(email="first@example.com")
    second_user = register_user(email="second@example.com")
    pdf = make_pdf()

    first = _upload(client, api_prefix, first_user["access_token"], pdf)
    second = _upload(client, api_prefix, second_user["access_token"], pdf)

    assert first.status_code == 202 and second.status_code == 202
    # One shared paper and two independent entries; the second upload joined
    # the run that was already active instead of starting another.
    assert db_session.scalar(select(func.count(PaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(UserPaperRecord.id))) == 2

    first_entry_id = client.get(
        f"{api_prefix}/papers", headers=auth_headers(first_user["access_token"])
    ).json()["items"][0]["id"]
    foreign_detail = client.get(
        f"{api_prefix}/papers/{first_entry_id}",
        headers=auth_headers(second_user["access_token"]),
    )
    foreign_pdf = client.get(
        f"{api_prefix}/papers/{first_entry_id}/pdf",
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
    storage: ObjectStorage,
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
                enrichment = MetadataEnricher(
                    storage=storage,
                    resolver=build_default_resolver(),
                    session_factory=session_factory,
                )
                from app.pipelines.runs import RunService

                yield PaperLibraryService(
                    papers,
                    RunService(session_factory=session_factory),
                    enrichment,
                    storage,
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
