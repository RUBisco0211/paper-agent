import hashlib
import json
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.library.repo import PaperRecord, UserPaperRecord
from app.platform.storage import ObjectStorage, mineru_artifact_key
from tests.conftest import auth_headers


def test_block_counts_caption_every_type_of_one_paper(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    storage: ObjectStorage,
    completed_imports,
) -> None:
    owner = register_user(email="block-counts@example.com")
    entry_id = _entry_id(client, api_prefix, owner["access_token"], make_pdf())
    paper = _paper_of(db_session, entry_id)
    index = {
        "types": ["text", "table"],
        "items": [
            {"id": 0, "type": "text", "page": 1, "text": "一"},
            {"id": 1, "type": "text", "page": 1, "text": "二"},
            {"id": 2, "type": "text", "page": 2, "text": "三"},
            {"id": 3, "type": "table", "page": 2, "text": "表"},
        ],
    }
    _publish(db_session, storage, paper, {"blocks_index.json": index})

    response = client.get(
        f"{api_prefix}/papers/{entry_id}/blocks",
        params={"type": "table", "limit": 1},
        headers=auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # 过滤后的 total 只数当前类别，counts 给出每个类别的数量。
    assert body["total"] == 1
    assert body["counts"] == {"text": 3, "table": 1}


def _entry_id(client: TestClient, api_prefix: str, token: str, pdf: bytes) -> UUID:
    response = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("counts.pdf", pdf, "application/pdf")},
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
    files: dict[str, dict],
) -> None:
    """Write parse artifacts the way the parse stage publishes them."""
    manifest_files = {}
    for name, payload in files.items():
        raw = json.dumps(payload).encode()
        key = mineru_artifact_key(paper.file_hash, name)
        storage.put_bytes(key, raw)
        manifest_files[name] = {
            "key": key,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
    manifest_key = mineru_artifact_key(paper.file_hash, "manifest.json")
    storage.put_bytes(
        manifest_key,
        json.dumps({"file_hash": paper.file_hash, "files": manifest_files}).encode(),
    )
    paper.artifact_manifest_key = manifest_key
    paper.has_parsed = True
    session.commit()
