from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.imports.repo import PaperImportRecord
from app.platform.config import settings
from app.platform.security import create_candidate_token
from tests.conftest import auth_headers


def test_approved_batch_imports_only_selected_candidates_once_when_user_confirms(
    client: TestClient, api_prefix: str, register_user, monkeypatch
) -> None:
    owner = register_user(email="approved-batch-owner@example.com")
    session_id = str(uuid4())
    client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    token = create_candidate_token(
        user_id=owner["user"]["id"],
        session_id=session_id,
        openalex_id="https://openalex.org/W1",
        identifier="10.1234/selected",
    )
    approval = client.post(
        f"{api_prefix}/imports/approvals",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id, "candidate_tokens": [token]},
    )
    assert approval.status_code == 201
    monkeypatch.setattr(settings, "agent_internal_key", "a" * 64)
    imports = []
    from app.imports.service import ImportService

    def fake_start(self, *, user_id, identifier_text, project_id=None):
        imports.append(identifier_text)
        return SimpleNamespace(id=uuid4(), identifier=identifier_text, status="queued")

    monkeypatch.setattr(ImportService, "start", fake_start)
    payload = {"user_id": owner["user"]["id"], "session_id": session_id}
    first = client.post(
        f"{api_prefix}/internal/import-approved",
        headers={"X-Agent-Internal-Key": "a" * 64},
        json=payload,
    )
    second = client.post(
        f"{api_prefix}/internal/import-approved",
        headers={"X-Agent-Internal-Key": "a" * 64},
        json=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert imports == ["10.1234/selected"]
    assert first.json() == second.json()


def test_another_user_cannot_approve_a_discovered_candidate(
    client: TestClient, api_prefix: str, register_user
) -> None:
    owner = register_user(email="approved-batch-owner-2@example.com")
    stranger = register_user(email="approved-batch-stranger@example.com")
    session_id = str(uuid4())
    client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    token = create_candidate_token(
        user_id=owner["user"]["id"],
        session_id=session_id,
        openalex_id="https://openalex.org/W1",
        identifier="10.1234/selected",
    )
    response = client.post(
        f"{api_prefix}/imports/approvals",
        headers=auth_headers(stranger["access_token"]),
        json={"session_id": session_id, "candidate_tokens": [token]},
    )
    assert response.status_code in {403, 404}


def test_user_can_approve_a_semantic_scholar_candidate_with_a_doi(
    client: TestClient, api_prefix: str, register_user
) -> None:
    owner = register_user(email="approved-semantic-scholar@example.com")
    session_id = str(uuid4())
    client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    token = create_candidate_token(
        user_id=owner["user"]["id"],
        session_id=session_id,
        source_id="https://www.semanticscholar.org/paper/abc",
        identifier="10.1234/selected",
    )
    response = client.post(
        f"{api_prefix}/imports/approvals",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id, "candidate_tokens": [token]},
    )
    assert response.status_code == 201


def test_import_queue_contains_only_the_current_users_imports(
    client: TestClient, api_prefix: str, register_user, db_session
) -> None:
    owner = register_user(email="queue-owner@example.com")
    stranger = register_user(email="queue-stranger@example.com")
    db_session.add_all([
        PaperImportRecord(
            user_id=user["user"]["id"], identifier_type="doi",
            identifier=identifier, status="queued",
        )
        for user, identifier in (
            (owner, "10.1234/owner"), (stranger, "10.1234/stranger")
        )
    ])
    db_session.commit()
    response = client.get(
        f"{api_prefix}/imports/queue",
        headers=auth_headers(owner["access_token"]),
    )
    assert response.status_code == 200
    assert [item["identifier"] for item in response.json()["items"]] == [
        "10.1234/owner"
    ]


def test_approved_batch_starts_a_real_import_when_the_agent_consumes_it(
    client: TestClient, api_prefix: str, register_user, monkeypatch
) -> None:
    owner = register_user(email="approved-real-import@example.com")
    session_id = str(uuid4())
    client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    token = create_candidate_token(
        user_id=owner["user"]["id"], session_id=session_id,
        openalex_id="https://openalex.org/W7148549932",
        identifier="10.48550/arXiv.2604.00722",
    )
    approval = client.post(
        f"{api_prefix}/imports/approvals",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id, "candidate_tokens": [token]},
    )
    assert approval.status_code == 201
    from app.imports.service import ImportService

    monkeypatch.setattr(ImportService, "_run_sync", lambda self, import_id: None)
    monkeypatch.setattr(settings, "agent_internal_key", "a" * 64)
    result = client.post(
        f"{api_prefix}/internal/import-approved",
        headers={"X-Agent-Internal-Key": "a" * 64},
        json={"user_id": owner["user"]["id"], "session_id": session_id},
    )
    assert result.status_code == 200
    assert result.json()["results"][0]["status"] == "queued"
