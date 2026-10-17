"""Real scheduler → wakeup dispatcher → ChatService → PostgreSQL lifecycle.

Only provider output and the remote business HTTP boundary are substituted.
"""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from agentscope.app.storage import (
    AgentData,
    AgentRecord,
    ChatModelConfig,
    ScheduleData,
    ScheduleRecord,
)
from agentscope.event import (
    ReplyEndEvent,
    ReplyStartEvent,
    TextBlockDeltaEvent,
    TextBlockEndEvent,
    TextBlockStartEvent,
)
from agentscope.types import ReplyFinishedReason
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.platform.config import settings
from tests.conftest import _ensure_database, _truncate_all


@pytest.mark.parametrize(
    "mode", ["success", "setup_failure", "runtime_failure", "mail_failure"]
)
def test_scheduled_runs_persist_independent_results_when_no_tool_is_called(
    tmp_path, monkeypatch, caplog, mode
):
    from agentscope.app._service import _chat

    from agent_service.main import create_agent_service_app
    from agent_service.paper_agent import PaperAgent

    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    requests = []
    delivered = asyncio.Event()

    async def handler(request):
        body = json.loads(request.content) if request.content else None
        requests.append((request.url.path, body))
        if request.url.path.endswith("schedule-results"):
            delivered.set()
            return httpx.Response(
                503 if mode == "mail_failure" else 200, json={"accepted": True}
            )
        return httpx.Response(200, json={})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            **kwargs, transport=httpx.MockTransport(handler)
        ),
    )

    async def get_model(*args):
        if mode == "setup_failure":
            raise RuntimeError("private provider details")
        return object()

    monkeypatch.setattr(_chat, "get_model", get_model)

    called = []

    async def reply_stream(self, inputs=None):
        called.append(self.state.session_id)
        reply_id, block_id = uuid4().hex, uuid4().hex
        yield ReplyStartEvent(
            session_id=self.state.session_id, reply_id=reply_id, name="Reader"
        )
        yield TextBlockStartEvent(reply_id=reply_id, block_id=block_id)
        yield TextBlockDeltaEvent(
            reply_id=reply_id, block_id=block_id, delta="Full final answer"
        )
        if mode == "runtime_failure":
            raise RuntimeError("private partial provider details")
        yield TextBlockEndEvent(reply_id=reply_id, block_id=block_id)
        yield ReplyEndEvent(session_id=self.state.session_id, reply_id=reply_id)

    monkeypatch.setattr(PaperAgent, "reply_stream", reply_stream)

    database_url = (
        make_url(settings.resolved_test_database_url)
        .set(
            database="paper_agent_lifecycle_test",
        )
        .render_as_string(hide_password=False)
    )
    _ensure_database(database_url)
    engine = create_engine(database_url)
    _truncate_all(engine)
    engine.dispose()
    app = create_agent_service_app(database_url, tmp_path)
    user_id = str(uuid4())

    async def exercise():
        async with app.router.lifespan_context(app):
            storage = app.state.storage
            agent = AgentRecord(
                user_id=user_id,
                data=AgentData.model_validate(
                    {
                        "name": "Reader",
                        "context_config": {},
                        "react_config": {},
                    }
                ),
            )
            await storage.upsert_agent(user_id, agent)
            schedule = ScheduleRecord(
                user_id=user_id,
                agent_id=agent.id,
                data=ScheduleData(
                    name="Daily review",
                    cron_expression="0 0 1 1 *",
                    enabled=False,
                    stateful=False,
                    chat_model_config=ChatModelConfig(
                        type="openai_credential",
                        credential_id="nonproduction",
                        model="deterministic",
                        parameters={},
                    ),
                ),
            )
            await storage.upsert_schedule(user_id, schedule)
            active = schedule.model_copy(
                update={"data": schedule.data.model_copy(update={"enabled": True})}
            )
            for _ in range(2):
                delivered.clear()
                await app.state.scheduler_manager._build_trigger(active)()
                await asyncio.wait_for(delivered.wait(), timeout=10)
                tasks = list(app.state.chat_run_registry._tasks.values())
                if tasks:
                    await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
            sessions = await storage.list_sessions(user_id, agent.id)
            assert len(sessions) == 2
            assert sessions[0].id != sessions[1].id
            for session in sessions:
                messages, _ = await storage.list_messages(user_id, session.id)
                expected = (
                    ReplyFinishedReason.ERROR
                    if mode in {"setup_failure", "runtime_failure"}
                    else ReplyFinishedReason.COMPLETED
                )
                assert messages[-1].finished_reason == expected

    asyncio.run(exercise())
    bindings = [body for path, body in requests if path.endswith("schedule-sessions")]
    results = [body for path, body in requests if path.endswith("schedule-results")]
    assert {b["session_id"] for b in bindings} == {r["session_id"] for r in results}
    assert len(results) == len(bindings) == 2
    assert len(called) == (0 if mode == "setup_failure" else 2)
    for result in results:
        assert result["name"] == "Daily review"
        assert result["markdown"] == (
            "" if mode in {"setup_failure", "runtime_failure"} else "Full final answer"
        )
        assert result["status"] == (
            "failed" if mode in {"setup_failure", "runtime_failure"} else "success"
        )
        assert "private" not in json.dumps(result)
    if mode == "mail_failure":
        assert "schedule_result_event_failed" in caplog.text
