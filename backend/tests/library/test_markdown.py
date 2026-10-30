import hashlib
import json
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.library.repo import PaperRecord, UserPaperRecord
from app.platform.storage import ObjectStorage, mineru_artifact_key
from tests.conftest import auth_headers

PDF_FILENAME = "full text.pdf"


def test_markdown_full_text_is_served_to_the_owner_with_its_images(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    storage: ObjectStorage,
    completed_imports,
) -> None:
    owner = register_user(email="markdown-owner@example.com")
    entry_id = _entry_id(client, api_prefix, owner["access_token"], make_pdf())
    paper = _paper_of(db_session, entry_id)
    markdown = b"# Title\n\nBody\n\n![figure](images/figure-1.png)\n"
    image = b"\x89PNG\r\n\x1a\npreview"
    _publish(db_session, storage, paper, {"full.md": markdown, "images/figure-1.png": image})

    response = client.get(
        f"{api_prefix}/papers/{entry_id}/markdown",
        headers=auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["markdown"] == markdown.decode()
    image_response = client.get(
        f"{api_prefix}/papers/{entry_id}/assets/images/figure-1.png",
        headers=auth_headers(owner["access_token"]),
    )
    assert image_response.status_code == 200, image_response.text
    assert image_response.content == image
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.headers["x-content-type-options"] == "nosniff"


def test_markdown_and_assets_stay_private_to_the_owner(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    storage: ObjectStorage,
    completed_imports,
) -> None:
    owner = register_user(email="markdown-private-owner@example.com")
    stranger = register_user(email="markdown-private-stranger@example.com")
    entry_id = _entry_id(client, api_prefix, owner["access_token"], make_pdf())
    paper = _paper_of(db_session, entry_id)
    _publish(
        db_session,
        storage,
        paper,
        {"full.md": b"# Title\n", "images/figure-1.png": b"\x89PNG\r\n\x1a\n"},
    )

    markdown = client.get(
        f"{api_prefix}/papers/{entry_id}/markdown",
        headers=auth_headers(stranger["access_token"]),
    )
    image = client.get(
        f"{api_prefix}/papers/{entry_id}/assets/images/figure-1.png",
        headers=auth_headers(stranger["access_token"]),
    )

    assert markdown.status_code == 404
    assert image.status_code == 404


def test_assets_outside_the_image_folder_are_never_served(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    storage: ObjectStorage,
    completed_imports,
) -> None:
    owner = register_user(email="markdown-asset-owner@example.com")
    entry_id = _entry_id(client, api_prefix, owner["access_token"], make_pdf())
    paper = _paper_of(db_session, entry_id)
    _publish(
        db_session,
        storage,
        paper,
        {
            "full.md": b"# Title\n",
            "content_list.json": b"[]",
            "images/figure-1.png": b"\x89PNG\r\n\x1a\n",
        },
    )

    for path in (
        "content_list.json",
        "manifest.json",
        "images/../content_list.json",
        "images/../../manifest.json",
    ):
        response = client.get(
            f"{api_prefix}/papers/{entry_id}/assets/{path}",
            headers=auth_headers(owner["access_token"]),
        )
        assert response.status_code == 404, (path, response.status_code)


def test_markdown_is_unavailable_when_the_parse_has_no_full_text(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    storage: ObjectStorage,
    completed_imports,
) -> None:
    owner = register_user(email="markdown-missing-owner@example.com")
    entry_id = _entry_id(client, api_prefix, owner["access_token"], make_pdf())
    paper = _paper_of(db_session, entry_id)
    _publish(db_session, storage, paper, {"content_list.json": b"[]"})

    response = client.get(
        f"{api_prefix}/papers/{entry_id}/markdown",
        headers=auth_headers(owner["access_token"]),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "paper_markdown_not_available"


def _entry_id(client: TestClient, api_prefix: str, token: str, pdf: bytes) -> UUID:
    response = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": (PDF_FILENAME, pdf, "application/pdf")},
    )
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


def _publish(
    session: Session,
    storage: ObjectStorage,
    paper: PaperRecord,
    files: dict[str, bytes],
) -> None:
    """Write parse artifacts the way the parse stage publishes them."""
    manifest_files = {}
    for name, payload in files.items():
        key = mineru_artifact_key(paper.file_hash, name)
        storage.put_bytes(key, payload)
        manifest_files[name] = {
            "key": key,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
    manifest_key = mineru_artifact_key(paper.file_hash, "manifest.json")
    storage.put_bytes(
        manifest_key,
        json.dumps({"file_hash": paper.file_hash, "files": manifest_files}).encode(),
    )
    paper.artifact_manifest_key = manifest_key
    paper.has_parsed = True
    session.commit()
