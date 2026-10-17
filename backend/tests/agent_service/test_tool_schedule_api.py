"""Agent schedule API inherits model settings from the source session."""

from types import SimpleNamespace
from typing import cast

import pytest
from agentscope.app.deps import get_scheduler_manager, get_storage
from agentscope.app.storage import ChatModelConfig, SessionSource, StorageBase
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.platform.config import settings


@pytest.mark.asyncio
async def test_agent_schedule_api_creates_disabled_stateless_task_from_owned_session():
    from agent_service.schedule_api import ToolScheduleCreate, create_tool_schedule

    stored = []

    class Storage:
        async def get_session(self, user_id, agent_id, session_id):
            return SimpleNamespace(
                user_id=user_id,
                agent_id=agent_id,
                source=SessionSource.USER,
                config=SimpleNamespace(
                    chat_model_config=ChatModelConfig(
                        type="openai_credential",
                        credential_id="credential-1",
                        model="configured",
                        parameters={},
                    )
                ),
            )

        async def upsert_schedule(self, user_id, schedule):
            stored.append(schedule)

    result = await create_tool_schedule(
        ToolScheduleCreate(
            user_id="user-1",
            agent_id="agent-1",
            session_id="session-1",
            name="Review",
            prompt="Review papers",
            cron_expression="30 9 * * MON",
            timezone="Asia/Shanghai",
        ),
        storage=cast(StorageBase, Storage()),
    )
    assert result.schedule_id == stored[0].id
    assert stored[0].data.enabled is False
    assert stored[0].data.stateful is False
    assert stored[0].data.source_session_id == "session-1"


def test_internal_schedule_http_route_requires_key_and_activates_bound_task(
    monkeypatch,
):
    from agent_service.schedule_api import router

    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    schedules = {}
    activated = []

    class Storage:
        async def get_session(self, user_id, agent_id, session_id):
            return SimpleNamespace(
                user_id=user_id,
                agent_id=agent_id,
                source=SessionSource.USER,
                config=SimpleNamespace(
                    chat_model_config=ChatModelConfig(
                        type="openai_credential",
                        credential_id="credential-1",
                        model="configured",
                        parameters={},
                    )
                ),
            )

        async def upsert_schedule(self, user_id, schedule):
            schedules[schedule.id] = schedule

        async def get_schedule(self, user_id, schedule_id):
            return schedules.get(schedule_id)

        async def delete_schedule(self, user_id, schedule_id):
            schedules.pop(schedule_id)

    class Scheduler:
        async def register_schedule(self, schedule):
            activated.append(schedule.id)

        async def remove_schedule(self, schedule_id):
            activated.remove(schedule_id)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_storage] = lambda: Storage()
    app.dependency_overrides[get_scheduler_manager] = lambda: Scheduler()
    body = {
        "user_id": "user-1",
        "agent_id": "agent-1",
        "session_id": "session-1",
        "name": "Review",
        "prompt": "Review papers",
        "cron_expression": "30 9 * * MON",
        "timezone": "Asia/Shanghai",
    }
    with TestClient(app) as client:
        assert client.post("/internal/tool-schedules", json=body).status_code == 401
        headers = {"X-Agent-Internal-Key": "test-internal-key"}
        created = client.post("/internal/tool-schedules", json=body, headers=headers)
        assert created.status_code == 201
        schedule_id = created.json()["schedule_id"]
        assert schedules[schedule_id].data.enabled is False
        assert (
            client.post(
                f"/internal/tool-schedules/{schedule_id}/enable",
                headers=headers,
                json={"user_id": "user-1"},
            ).status_code
            == 204
        )
        assert activated == [schedule_id]
        assert (
            client.request(
                "DELETE",
                f"/internal/tool-schedules/{schedule_id}",
                headers=headers,
                json={"user_id": "user-1"},
            ).status_code
            == 204
        )
        assert schedule_id not in schedules


@pytest.mark.asyncio
async def test_agent_schedule_api_rejects_creation_during_an_unattended_run():
    from fastapi import HTTPException

    from agent_service.schedule_api import ToolScheduleCreate, create_tool_schedule

    class Storage:
        async def get_session(self, user_id, agent_id, session_id):
            return SimpleNamespace(
                user_id=user_id,
                agent_id=agent_id,
                source=SessionSource.SCHEDULE,
                config=SimpleNamespace(chat_model_config=object()),
            )

    with pytest.raises(HTTPException) as error:
        await create_tool_schedule(
            ToolScheduleCreate(
                user_id="user-1",
                agent_id="agent-1",
                session_id="run-1",
                name="Repeat",
                prompt="Keep repeating",
                cron_expression="0 9 * * MON",
                timezone="Asia/Shanghai",
            ),
            storage=cast(StorageBase, Storage()),
        )
    assert error.value.status_code == 409
