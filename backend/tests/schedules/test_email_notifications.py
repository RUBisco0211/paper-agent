"""Notification settings are owner scoped and persisted in PostgreSQL."""

from uuid import uuid4

from tests.conftest import auth_headers


def test_schedule_binding_defaults_email_off_when_created_without_choice(
    client, register_user
):
    owner = register_user()
    response = client.post(
        "/v1/schedule-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"schedule_id": uuid4().hex},
    )
    assert response.status_code == 201
    assert response.json()["notify_email"] is False


def test_schedule_binding_persists_email_choice_when_owner_updates_task(
    client, register_user
):
    owner = register_user()
    headers = auth_headers(owner["access_token"])
    schedule_id = uuid4().hex
    created = client.post(
        "/v1/schedule-bindings",
        headers=headers,
        json={"schedule_id": schedule_id, "notify_email": True},
    )
    assert created.status_code == 201
    assert created.json()["notify_email"] is True
    changed = client.patch(
        f"/v1/schedules/{schedule_id}", headers=headers, json={"notify_email": False}
    )
    assert changed.status_code == 200
    assert changed.json()["notify_email"] is False
    assert (
        client.get("/v1/schedule-bindings", headers=headers).json()[0]["notify_email"]
        is False
    )


def test_schedule_setting_rejects_changes_when_task_belongs_to_another_user(
    client, register_user
):
    owner = register_user()
    other = register_user(email="other@example.com")
    schedule_id = uuid4().hex
    client.post(
        "/v1/schedule-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"schedule_id": schedule_id},
    )
    denied = client.patch(
        f"/v1/schedules/{schedule_id}",
        headers=auth_headers(other["access_token"]),
        json={"notify_email": True},
    )
    assert denied.status_code == 404


def test_agent_created_schedule_keeps_email_choice_when_user_requests_notification(
    client, register_user, monkeypatch
):
    from app.platform.config import settings
    from app.schedules.depends import get_agent_schedule_gateway

    owner = register_user()
    headers = auth_headers(owner["access_token"])
    session_id = uuid4().hex
    assert (
        client.post(
            "/v1/session-bindings", headers=headers, json={"session_id": session_id}
        ).status_code
        == 201
    )
    schedule_id = uuid4().hex

    class Gateway:
        def create_disabled(self, **kwargs):
            return schedule_id

        def enable(self, **kwargs):
            return None

        def delete(self, **kwargs):
            return None

    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    client.app.dependency_overrides[get_agent_schedule_gateway] = lambda: Gateway()
    result = client.post(
        "/v1/internal/agent-schedules",
        headers={"X-Agent-Internal-Key": "test-internal-key"},
        json={
            "user_id": owner["user"]["id"],
            "session_id": session_id,
            "agent_id": "reader",
            "name": "Review",
            "prompt": "Read",
            "time": "09:00",
            "weekdays": ["mon"],
            "notify_email": True,
        },
    )
    assert result.status_code == 201
    assert result.json()["notify_email"] is True
    assert (
        client.get("/v1/schedule-bindings", headers=headers).json()[0]["notify_email"]
        is True
    )
