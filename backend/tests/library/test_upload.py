import hashlib
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.repo import (
    IngestionJobRecord,
    IngestionRepository,
    IngestionStageRecordOrm,
)
from app.ingestion.service import IngestionService
from app.library.depends import (
    get_paper_library_service,
)
from app.library.repo import PaperRecord, PaperRepository, UserPaperRecord
from app.library.service import PaperLibraryService
from app.platform.storage import (
    ObjectStorage,
    mineru_artifact_key,
    mineru_job_artifact_key,
)
from app.scholar.metadata import MetadataResolver
from tests.conftest import auth_headers

PDF_FILENAME = "attention is all you need.pdf"


def test_legacy_paper_image_can_be_previewed_from_its_own_storage_prefix(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    storage: ObjectStorage,
) -> None:
    owner = register_user(email="legacy-image-owner@example.com")
    entry_id = UUID(
        _upload(client, api_prefix, owner["access_token"], make_pdf()).json()["paper"][
            "id"
        ]
    )
    paper = db_session.get(
        PaperRecord, db_session.get(UserPaperRecord, entry_id).paper_id
    )
    paper.has_fulltext = True
    db_session.commit()
    storage.put_bytes(
        mineru_artifact_key(paper.file_hash, "content_list.json"),
        json.dumps(
            [{"type": "image", "page_idx": 0, "img_path": "images/figure.png"}]
        ).encode(),
    )
    payload = b"\x89PNG\r\n\x1a\nlegacy"
    storage.put_bytes(
        mineru_artifact_key(paper.file_hash, "images/images/figure.png"), payload
    )

    response = client.get(
        f"{api_prefix}/papers/{entry_id}/blocks/0/image",
        headers=auth_headers(owner["access_token"]),
    )
    assert response.status_code == 200
    assert response.content == payload


def test_legacy_block_image_revalidates_when_it_is_still_available(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    storage: ObjectStorage,
) -> None:
    owner = register_user(email="legacy-cache@example.com")
    entry_id = UUID(_upload(client, api_prefix, owner["access_token"], make_pdf()).json()["paper"]["id"])
    paper = db_session.get(PaperRecord, db_session.get(UserPaperRecord, entry_id).paper_id)
    paper.has_fulltext = True
    db_session.commit()
    content_key = mineru_artifact_key(paper.file_hash, "content_list.json")
    image_key = mineru_artifact_key(paper.file_hash, "images/figure.png")
    storage.put_bytes(content_key, json.dumps([{"type": "image", "page_idx": 0, "img_path": "figure.png"}]).encode())
    storage.put_bytes(image_key, b"\x89PNG\r\n\x1a\npreview")
    url = f"{api_prefix}/papers/{entry_id}/blocks/0/image"
    first = client.get(url, headers=auth_headers(owner["access_token"]))
    assert first.status_code == 200
    etag = first.headers["etag"]
    repeated = client.get(url, headers={**auth_headers(owner["access_token"]), "If-None-Match": etag})
    assert repeated.status_code == 304
    storage.delete(image_key)
    missing = client.get(url, headers={**auth_headers(owner["access_token"]), "If-None-Match": etag})
    assert missing.status_code == 404


def test_paper_blocks_are_filtered_and_private(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    storage: ObjectStorage,
) -> None:
    owner = register_user(email="block-owner@example.com")
    stranger = register_user(email="block-stranger@example.com")
    entry_id = UUID(
        _upload(client, api_prefix, owner["access_token"], make_pdf()).json()["paper"][
            "id"
        ]
    )
    paper = db_session.get(
        PaperRecord, db_session.get(UserPaperRecord, entry_id).paper_id
    )
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
    key = mineru_job_artifact_key(paper.file_hash, "test", "blocks_index.json")
    payload = json.dumps(index).encode()
    storage.put_bytes(key, payload)
    content_key = mineru_job_artifact_key(paper.file_hash, "test", "content_list.json")
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
    image_key = mineru_job_artifact_key(paper.file_hash, "test", "images/figure-1.png")
    image_payload = b"\x89PNG\r\n\x1a\npreview"
    storage.put_bytes(image_key, image_payload)
    manifest_key = mineru_job_artifact_key(paper.file_hash, "test", "manifest.json")
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
    paper.has_fulltext = True
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


class _NoopPdfFetcher:
    def download(self, url: str, *, destination: Path):
        raise AssertionError("该用例不应下载 PDF")


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
    # The job ran inline: local recognition finished, MinerU is unconfigured.
    assert paper["processing"]["status"] == "failed"

    job = body["ingestion_job"]
    assert job["paper_id"] == paper["id"]
    assert job["status"] == "failed"
    assert job["error_code"] == "provider_not_configured"
    stages = {stage["stage"]: stage for stage in job["stages"]}
    assert set(stages) == {"metadata", "fulltext", "chunking", "embedding"}
    assert stages["metadata"]["status"] == "succeeded"
    assert stages["metadata"]["progress"]["outcome"] == "unrecognized"
    assert stages["fulltext"]["status"] == "failed"
    assert stages["fulltext"]["error_code"] == "provider_not_configured"
    # Blocking failure stops later stages instead of pretending they ran.
    assert stages["chunking"]["status"] == "pending"
    assert stages["embedding"]["status"] == "pending"

    assert db_session.scalar(select(func.count(PaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(UserPaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(IngestionJobRecord.id))) == 1
    assert db_session.scalar(select(func.count(IngestionStageRecordOrm.id))) == 4


def test_duplicate_upload_reuses_paper_and_entry(
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
    # The upload never duplicates the shared paper or the user's entry; the
    # second upload only asks for the stages that are still missing.
    assert db_session.scalar(select(func.count(PaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(UserPaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(IngestionJobRecord.id))) == 2


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
                yield PaperLibraryService(
                    papers,
                    IngestionService(IngestionRepository(session), papers),
                    storage,
                    MetadataResolver([]),
                    _NoopPdfFetcher(),  # type: ignore[arg-type]
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
