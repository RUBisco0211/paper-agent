"""The agent reads a page or a block image only inside the bound session scope."""

import base64
import hashlib
import json
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.library.repo import PaperRecord, UserPaperRecord
from app.platform.config import settings
from app.platform.storage import mineru_artifact_key
from app.sessions.repo import BoundCitationRecord
from tests.conftest import auth_headers
from tests.retrieval.test_search_api import _upload

INTERNAL_KEY = "a" * 64

CONTENT = [
    {"type": "text", "page_idx": 0, "text": "First page body"},
    {"type": "text", "page_idx": 1, "text": "Second page body"},
    {
        "type": "image",
        "page_idx": 1,
        "img_path": "images/figure-1.png",
        "img_caption": ["Figure 1: accuracy"],
    },
]
IMAGE_BYTES = b"\x89PNG\r\n\x1a\npage-figure"


def _seed_artifacts(
    db_session: Session, storage, user_paper_id: str, content: list[dict] | None = None
) -> None:
    """Replace the stub artifacts with a two-page document holding one image."""
    user_paper = db_session.get(UserPaperRecord, UUID(user_paper_id))
    paper = db_session.get(PaperRecord, user_paper.paper_id)
    file_hash = paper.file_hash
    content_payload = json.dumps(content or CONTENT).encode()
    image_key = mineru_artifact_key(file_hash, "images/figure-1.png")
    storage.put_bytes(image_key, IMAGE_BYTES)
    content_key = mineru_artifact_key(file_hash, "content_list.json")
    storage.put_bytes(content_key, content_payload)
    manifest_key = mineru_artifact_key(file_hash, "manifest.json")
    storage.put_bytes(
        manifest_key,
        json.dumps(
            {
                "file_hash": file_hash,
                "files": {
                    "content_list.json": {
                        "key": content_key,
                        "sha256": hashlib.sha256(content_payload).hexdigest(),
                    },
                    "images/figure-1.png": {
                        "key": image_key,
                        "bytes": len(IMAGE_BYTES),
                        "sha256": hashlib.sha256(IMAGE_BYTES).hexdigest(),
                    },
                },
            }
        ).encode(),
    )
    paper.artifact_manifest_key = manifest_key
    db_session.commit()


def _bound_session(client: TestClient, api_prefix: str, token: str) -> str:
    session_id = str(uuid4())
    created = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(token),
        json={"session_id": session_id},
    )
    assert created.status_code == 201, created.text
    return session_id


def test_page_read_returns_the_requested_page_when_the_paper_is_in_scope(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    storage,
    db_session,
    completed_imports,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", INTERNAL_KEY)
    user = register_user()
    paper_id = _upload(
        client, api_prefix, user["access_token"], make_pdf(page_count=2)
    )
    _seed_artifacts(db_session, storage, paper_id)
    session_id = _bound_session(client, api_prefix, user["access_token"])

    response = client.post(
        f"{api_prefix}/internal/paper-page",
        headers={"X-Agent-Internal-Key": INTERNAL_KEY},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "paper_id": paper_id,
            "page": 2,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page"] == 2
    assert body["total_pages"] == 2
    assert "Second page body" in body["markdown"]
    assert "First page body" not in body["markdown"]
    assert [item["block_id"] for item in body["images"]] == [2]
    assert body["images"][0]["caption"] == "Figure 1: accuracy"


def test_page_read_rejects_a_paper_outside_the_bound_project_when_scope_is_project(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    storage,
    db_session,
    completed_imports,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", INTERNAL_KEY)
    user = register_user()
    inside = _upload(
        client, api_prefix, user["access_token"], make_pdf(page_count=2)
    )
    outside = _upload(
        client, api_prefix, user["access_token"], make_pdf(page_count=3)
    )
    assert inside != outside
    _seed_artifacts(db_session, storage, inside)
    project = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(user["access_token"]),
        json={"name": "Scoped"},
    ).json()
    client.post(
        f"{api_prefix}/projects/{project['id']}/papers",
        headers=auth_headers(user["access_token"]),
        json={"paper_ids": [inside]},
    )
    session_id = str(uuid4())
    bound = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(user["access_token"]),
        json={"session_id": session_id, "project_id": project["id"]},
    )
    assert bound.status_code == 201, bound.text

    response = client.post(
        f"{api_prefix}/internal/paper-page",
        headers={"X-Agent-Internal-Key": INTERNAL_KEY},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "paper_id": outside,
            "page": 1,
        },
    )

    assert response.status_code == 404
    assert response.json()["message"] == "文献不在当前会话范围"


def test_page_read_rejects_a_page_beyond_the_document_when_page_is_too_large(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    storage,
    db_session,
    completed_imports,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", INTERNAL_KEY)
    user = register_user()
    paper_id = _upload(
        client, api_prefix, user["access_token"], make_pdf(page_count=2)
    )
    _seed_artifacts(db_session, storage, paper_id)
    session_id = _bound_session(client, api_prefix, user["access_token"])

    response = client.post(
        f"{api_prefix}/internal/paper-page",
        headers={"X-Agent-Internal-Key": INTERNAL_KEY},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "paper_id": paper_id,
            "page": 9,
        },
    )

    assert response.status_code == 422
    assert "共 2 页" in response.json()["message"]


def test_image_read_returns_the_block_image_when_the_block_has_one(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    storage,
    db_session,
    completed_imports,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", INTERNAL_KEY)
    user = register_user()
    paper_id = _upload(
        client, api_prefix, user["access_token"], make_pdf(page_count=2)
    )
    _seed_artifacts(db_session, storage, paper_id)
    session_id = _bound_session(client, api_prefix, user["access_token"])

    response = client.post(
        f"{api_prefix}/internal/paper-image",
        headers={"X-Agent-Internal-Key": INTERNAL_KEY},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "paper_id": paper_id,
            "block_id": 2,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert base64.b64decode(body["image_base64"]) == IMAGE_BYTES
    assert body["image_media_type"] == "image/png"
    assert body["page"] == 2
    assert body["caption"] == "Figure 1: accuracy"


def test_image_read_rejects_a_block_without_a_picture_when_none_is_stored(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    storage,
    db_session,
    completed_imports,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", INTERNAL_KEY)
    user = register_user()
    paper_id = _upload(
        client, api_prefix, user["access_token"], make_pdf(page_count=2)
    )
    _seed_artifacts(db_session, storage, paper_id)
    session_id = _bound_session(client, api_prefix, user["access_token"])

    response = client.post(
        f"{api_prefix}/internal/paper-image",
        headers={"X-Agent-Internal-Key": INTERNAL_KEY},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "paper_id": paper_id,
            "block_id": 0,
        },
    )

    assert response.status_code == 404
    assert response.json()["message"] == "该片段没有图片"


def test_page_read_leaves_the_session_without_citations_when_a_page_is_read(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    storage,
    db_session,
    completed_imports,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", INTERNAL_KEY)
    user = register_user()
    paper_id = _upload(
        client, api_prefix, user["access_token"], make_pdf(page_count=2)
    )
    _seed_artifacts(db_session, storage, paper_id)
    session_id = _bound_session(client, api_prefix, user["access_token"])

    response = client.post(
        f"{api_prefix}/internal/paper-page",
        headers={"X-Agent-Internal-Key": INTERNAL_KEY},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "paper_id": paper_id,
            "page": 1,
        },
    )

    assert response.status_code == 200, response.text
    citations = db_session.query(BoundCitationRecord).filter_by(
        session_id=UUID(session_id)
    )
    assert citations.count() == 0


def test_page_read_omits_a_picture_that_cannot_be_served_when_it_is_missing(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    storage,
    db_session,
    completed_imports,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", INTERNAL_KEY)
    user = register_user()
    paper_id = _upload(
        client, api_prefix, user["access_token"], make_pdf(page_count=2)
    )
    _seed_artifacts(
        db_session,
        storage,
        paper_id,
        content=[
            {"type": "text", "page_idx": 1, "text": "Second page body"},
            {
                "type": "image",
                "page_idx": 1,
                "img_path": "images/missing.png",
                "img_caption": ["Missing figure"],
            },
        ],
    )
    session_id = _bound_session(client, api_prefix, user["access_token"])

    response = client.post(
        f"{api_prefix}/internal/paper-page",
        headers={"X-Agent-Internal-Key": INTERNAL_KEY},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "paper_id": paper_id,
            "page": 2,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["images"] == []
    assert "block 1" not in response.json()["markdown"]


def test_image_read_refuses_a_picture_above_the_configured_size(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    storage,
    db_session,
    completed_imports,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", INTERNAL_KEY)
    monkeypatch.setattr(settings, "paper_image_max_bytes", 4)
    user = register_user()
    paper_id = _upload(
        client, api_prefix, user["access_token"], make_pdf(page_count=2)
    )
    _seed_artifacts(db_session, storage, paper_id)
    session_id = _bound_session(client, api_prefix, user["access_token"])

    response = client.post(
        f"{api_prefix}/internal/paper-image",
        headers={"X-Agent-Internal-Key": INTERNAL_KEY},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "paper_id": paper_id,
            "block_id": 2,
        },
    )

    assert response.status_code == 422
    assert response.json()["message"] == "该图片过大，无法读取"
