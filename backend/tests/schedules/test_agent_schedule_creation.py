"""Agent-created schedules use the bound session scope and a narrow cadence."""

from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.platform.config import settings
from app.schedules.domain import weekly_cron
from app.schedules.repo import ScheduleBindingRepository
from tests.conftest import auth_headers


def test_weekly_cron_uses_named_days_and_validates_time():
    assert (
        weekly_cron(
            time="09:30", weekdays=["mon", "wed", "fri"], timezone="Asia/Shanghai"
        )
        == "30 9 * * MON,WED,FRI"
    )
    with pytest.raises(ValueError):
        weekly_cron(time="25:00", weekdays=["mon"], timezone="Asia/Shanghai")
    with pytest.raises(ValueError):
        weekly_cron(time="09:30", weekdays=[], timezone="Asia/Shanghai")
    with pytest.raises(ValueError):
        weekly_cron(time="09:30", weekdays=["mon"], timezone="Invalid/Zone")


def test_agent_schedule_creation_inherits_its_session_project(
    client: TestClient, api_prefix: str, register_user, monkeypatch
):
    from app.schedules.depends import get_agent_schedule_gateway

    owner = register_user()
    headers = auth_headers(owner["access_token"])
    project = client.post(
        f"{api_prefix}/projects", headers=headers, json={"name": "Review"}
    ).json()
    session_id = str(uuid4())
    timezone_update = client.patch(
        f"{api_prefix}/auth/timezone",
        headers=headers,
        json={"timezone": "Europe/Berlin"},
    )
    assert timezone_update.status_code == 200
    assert (
        client.post(
            f"{api_prefix}/session-bindings",
            headers=headers,
            json={"session_id": session_id, "project_id": project["id"]},
        ).status_code
        == 201
    )
    calls = []
    app = cast(FastAPI, client.app)

    class Gateway:
        def create_disabled(self, **kwargs):
            calls.append(("create", kwargs))
            return "schedule-agent-test"

        def enable(self, **kwargs):
            calls.append(("enable", kwargs))

        def delete(self, **kwargs):
            calls.append(("delete", kwargs))

    app.dependency_overrides[get_agent_schedule_gateway] = lambda: Gateway()
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    try:
        response = client.post(
            f"{api_prefix}/internal/agent-schedules",
            headers={"X-Agent-Internal-Key": "test-internal-key"},
            json={
                "user_id": owner["user"]["id"],
                "agent_id": "agent-test",
                "session_id": session_id,
                "name": "每周回顾",
                "prompt": "总结本周的文献",
                "time": "09:30",
                "weekdays": ["mon", "fri"],
            },
        )
    finally:
        app.dependency_overrides.pop(get_agent_schedule_gateway, None)
    assert response.status_code == 201
    assert response.json() == {
        "notify_email": False,
        "schedule_id": "schedule-agent-test",
        "project_id": project["id"],
        "cron_expression": "30 9 * * MON,FRI",
        "name": "每周回顾",
        "prompt": "总结本周的文献",
        "time": "09:30",
        "timezone": "Europe/Berlin",
        "weekdays": ["mon", "fri"],
    }
    assert [call[0] for call in calls] == ["create", "enable"]
    assert calls[0][1]["user_id"] == owner["user"]["id"]
    assert calls[0][1]["session_id"] == session_id.replace("-", "")


def test_agent_schedule_creation_removes_binding_when_activation_fails(
    client: TestClient, api_prefix: str, register_user, db_session, monkeypatch
):
    from app.schedules.depends import get_agent_schedule_gateway

    owner = register_user()
    session_id = str(uuid4())
    assert (
        client.post(
            f"{api_prefix}/session-bindings",
            headers=auth_headers(owner["access_token"]),
            json={"session_id": session_id, "project_id": None},
        ).status_code
        == 201
    )
    deleted = []
    app = cast(FastAPI, client.app)

    class Gateway:
        def create_disabled(self, **kwargs):
            return "schedule-to-rollback"

        def enable(self, **kwargs):
            raise RuntimeError("scheduler failed")

        def delete(self, **kwargs):
            deleted.append(kwargs["schedule_id"])

    app.dependency_overrides[get_agent_schedule_gateway] = lambda: Gateway()
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    try:
        with pytest.raises(RuntimeError, match="scheduler failed"):
            client.post(
                f"{api_prefix}/internal/agent-schedules",
                headers={"X-Agent-Internal-Key": "test-internal-key"},
                json={
                    "user_id": owner["user"]["id"],
                    "agent_id": "agent-test",
                    "session_id": session_id,
                    "name": "每周回顾",
                    "prompt": "总结文献",
                    "time": "09:30",
                    "timezone": "Asia/Shanghai",
                    "weekdays": ["mon"],
                },
            )
    finally:
        app.dependency_overrides.pop(get_agent_schedule_gateway, None)
    assert deleted == ["schedule-to-rollback"]
    assert ScheduleBindingRepository(db_session).get("schedule-to-rollback") is None

def test_agent_schedule_creation_follows_the_saved_notification_default(
    client: TestClient, api_prefix: str, register_user, monkeypatch
):
    from app.schedules.depends import get_agent_schedule_gateway

    owner = register_user()
    headers = auth_headers(owner["access_token"])
    assert (
        client.patch(
            f"{api_prefix}/auth/preferences",
            headers=headers,
            json={"notify_email_default": True},
        ).status_code
        == 200
    )
    session_id = str(uuid4())
    assert (
        client.post(
            f"{api_prefix}/session-bindings",
            headers=headers,
            json={"session_id": session_id, "project_id": None},
        ).status_code
        == 201
    )
    app = cast(FastAPI, client.app)

    class Gateway:
        def create_disabled(self, **_kwargs):
            return "schedule-follows-default"

        def enable(self, **_kwargs):
            return None

        def delete(self, **_kwargs):
            return None

    app.dependency_overrides[get_agent_schedule_gateway] = lambda: Gateway()
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    try:
        response = client.post(
            f"{api_prefix}/internal/agent-schedules",
            headers={"X-Agent-Internal-Key": "test-internal-key"},
            json={
                "user_id": owner["user"]["id"],
                "agent_id": "agent-test",
                "session_id": session_id,
                "name": "每日提醒",
                "prompt": "看看今天的文献",
                "time": "08:00",
                "weekdays": ["mon"],
            },
        )
    finally:
        app.dependency_overrides.pop(get_agent_schedule_gateway, None)

    assert response.status_code == 201
    assert response.json()["notify_email"] is True
