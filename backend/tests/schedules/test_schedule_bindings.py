"""Scheduled sessions inherit only their owning project's paper scope."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.platform.config import settings
from tests.conftest import auth_headers


def test_schedule_binding_prepares_each_run_scope_when_schedule_belongs_to_user(
    client: TestClient,
    api_prefix: str,
    register_user,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    owner = register_user()
    headers = auth_headers(owner["access_token"])
    project = client.post(
        f"{api_prefix}/projects", headers=headers, json={"name": "Review"}
    ).json()
    schedule_id = str(uuid4())
    created = client.post(
        f"{api_prefix}/schedule-bindings",
        headers=headers,
        json={"schedule_id": schedule_id, "project_id": project["id"]},
    )
    assert created.status_code == 201
    assert created.json()["project_id"] == project["id"]

    session_id = str(uuid4())
    payload = {
        "schedule_id": schedule_id,
        "session_id": session_id,
        "user_id": owner["user"]["id"],
    }
    internal_headers = {"X-Agent-Internal-Key": "test-internal-key"}
    first = client.post(
        f"{api_prefix}/internal/schedule-sessions",
        headers=internal_headers,
        json=payload,
    )
    assert first.status_code == 200
    assert first.json()["project_id"] == project["id"]
    second = client.post(
        f"{api_prefix}/internal/schedule-sessions",
        headers=internal_headers,
        json=payload,
    )
    assert second.status_code == 200
    assert second.json() == first.json()
    ordinary = client.get(f"{api_prefix}/session-bindings", headers=headers)
    assert ordinary.status_code == 200
    assert ordinary.json()["items"] == []
    blocked = client.delete(f"{api_prefix}/projects/{project['id']}", headers=headers)
    assert blocked.status_code == 409


def test_schedule_binding_rejects_other_users_project_and_unregistered_run(
    client: TestClient,
    api_prefix: str,
    register_user,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    owner = register_user()
    other = register_user(email="other@example.com")
    project = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(owner["access_token"]),
        json={"name": "Private"},
    ).json()
    denied = client.post(
        f"{api_prefix}/schedule-bindings",
        headers=auth_headers(other["access_token"]),
        json={"schedule_id": str(uuid4()), "project_id": project["id"]},
    )
    assert denied.status_code == 404

    unregistered = client.post(
        f"{api_prefix}/internal/schedule-sessions",
        headers={"X-Agent-Internal-Key": "test-internal-key"},
        json={
            "schedule_id": str(uuid4()),
            "session_id": str(uuid4()),
            "user_id": owner["user"]["id"],
        },
    )
    assert unregistered.status_code == 404


def test_global_schedule_binds_a_run_to_the_users_library_scope(
    client: TestClient,
    api_prefix: str,
    register_user,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    owner = register_user()
    other = register_user(email="scheduled-other@example.com")
    schedule_id = str(uuid4())
    created = client.post(
        f"{api_prefix}/schedule-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"schedule_id": schedule_id, "project_id": None},
    )
    assert created.status_code == 201
    assert created.json()["project_id"] is None

    payload = {
        "schedule_id": schedule_id,
        "session_id": str(uuid4()),
        "user_id": owner["user"]["id"],
    }
    prepared = client.post(
        f"{api_prefix}/internal/schedule-sessions",
        headers={"X-Agent-Internal-Key": "test-internal-key"},
        json=payload,
    )
    assert prepared.status_code == 200
    assert prepared.json()["project_id"] is None

    payload["user_id"] = other["user"]["id"]
    denied = client.post(
        f"{api_prefix}/internal/schedule-sessions",
        headers={"X-Agent-Internal-Key": "test-internal-key"},
        json=payload,
    )
    assert denied.status_code == 404
