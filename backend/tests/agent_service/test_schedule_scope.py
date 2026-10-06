import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from agent_service.retrieval_tools import prepare_schedule_scope
from app.platform.config import settings


class FakeStorage:
    def __init__(self, record) -> None:
        self.record = record

    async def get_session(self, user_id: str, agent_id: str, session_id: str):
        return self.record


def test_schedule_run_binds_project_before_agent_tools_when_session_is_scheduled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, json={"schedule_id": "task-1", "project_id": str(uuid4())}
        )

    async def check() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://business"
        ) as client:
            await prepare_schedule_scope(
                FakeStorage(
                    SimpleNamespace(source="schedule", source_schedule_id="task-1")
                ),
                str(uuid4()),
                "agent",
                str(uuid4()),
                client=client,
            )

    asyncio.run(check())
    assert len(calls) == 1
    assert calls[0].url.path.endswith("/internal/schedule-sessions")


def test_schedule_run_stops_when_project_binding_fails(monkeypatch) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "not_found"})

    async def check() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://business"
        ) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await prepare_schedule_scope(
                    FakeStorage(
                        SimpleNamespace(source="schedule", source_schedule_id="missing")
                    ),
                    str(uuid4()),
                    "agent",
                    str(uuid4()),
                    client=client,
                )

    asyncio.run(check())
