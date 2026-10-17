"""Notification recovery uses real AgentScope PostgreSQL records, never Agent reruns."""

import asyncio
from uuid import uuid4

import httpx
import pytest
from agentscope.app.storage import (
    ScheduleData,
    ScheduleRecord,
    SessionConfig,
    SessionSource,
)
from agentscope.message import Msg, TextBlock
from agentscope.state import AgentState
from agentscope.types import ReplyFinishedReason
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from agent_service.credential_storage import EncryptedCredentialStorage
from app.platform.config import settings
from tests.conftest import _ensure_database, _truncate_all


@pytest.fixture
async def notification_storage(monkeypatch):
    from agent_service import schedule_notifications as notifications

    url = (
        make_url(settings.resolved_test_database_url)
        .set(database="paper_agent_notify_test")
        .render_as_string(hide_password=False)
    )
    _ensure_database(url)
    engine = create_engine(url)
    _truncate_all(engine)
    engine.dispose()
    calls = []
    remote = {
        "unavailable": False,
        "scope_unavailable": False,
        "now": notifications.time.time(),
        "delivered": asyncio.Event(),
        "loop": notifications.ScheduleNotificationStorage._notification_loop,
    }
    monkeypatch.setattr(notifications.time, "time", lambda: remote["now"])

    async def no_background_scan(self):
        await asyncio.Event().wait()

    async def scope(*args, **kwargs):
        if remote["scope_unavailable"]:
            raise httpx.ConnectError("offline")

    async def request(method, path, **kwargs):
        calls.append(kwargs["json"])
        if remote["unavailable"]:
            raise httpx.ConnectError("offline")
        if remote.get("deleted"):
            request = httpx.Request(
                "POST", "http://business/v1/internal/schedule-results"
            )
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)
        remote["delivered"].set()
        return {"accepted": True}

    monkeypatch.setattr(
        notifications.ScheduleNotificationStorage,
        "_notification_loop",
        no_background_scan,
    )
    monkeypatch.setattr(notifications, "prepare_schedule_scope", scope)
    monkeypatch.setattr(notifications, "business_request", request)
    async with notifications.ScheduleNotificationStorage(
        url,
        key_provider=lambda: "a" * 64,
        create_tables=False,
        auto_migrate=True,
    ) as storage:
        yield storage, calls, remote


async def scheduled_session(storage):
    from agentscope.app.storage import ChatModelConfig

    user, agent = str(uuid4()), uuid4().hex
    schedule = ScheduleRecord(
        user_id=user,
        agent_id=agent,
        data=ScheduleData(
            name="Review",
            cron_expression="0 0 1 1 *",
            enabled=False,
            chat_model_config=ChatModelConfig(
                type="openai_credential",
                credential_id="fake",
                model="fake",
                parameters={},
            ),
        ),
    )
    await storage.upsert_schedule(user, schedule)
    session = await storage.upsert_session(
        user,
        agent,
        SessionConfig(workspace_id=""),
        source=SessionSource.SCHEDULE,
        source_schedule_id=schedule.id,
    )
    return session


def answer(text):
    return Msg(
        name="Reader",
        role="assistant",
        content=[TextBlock(text=text)],
        finished_reason=ReplyFinishedReason.COMPLETED,
    )


async def test_notification_remains_pending_when_business_event_submission_fails(
    notification_storage,
):
    storage, calls, remote = notification_storage
    session = await scheduled_session(storage)
    remote["unavailable"] = True
    await storage.upsert_message(session.user_id, session.id, answer("Original answer"))
    saved = await storage.get_session(session.user_id, session.agent_id, session.id)
    assert saved.state.middle_context["schedule_notification"]["status"] == "pending"
    remote["unavailable"] = False
    remote["now"] += 20
    await storage.recover_pending_notifications()
    saved = await storage.get_session(session.user_id, session.agent_id, session.id)
    assert saved.state.middle_context["schedule_notification"]["status"] == "delivered"
    assert len(calls) == 2


async def test_notification_marker_survives_when_chatservice_persists_stale_agent_state(
    notification_storage,
):
    storage, _, _ = notification_storage
    session = await scheduled_session(storage)
    await storage.upsert_message(session.user_id, session.id, answer("Original answer"))
    await storage.update_session_state(
        session.user_id, session.agent_id, session.id, AgentState()
    )
    saved = await storage.get_session(session.user_id, session.agent_id, session.id)
    assert saved.state.middle_context["schedule_notification"]["status"] == "delivered"


async def test_notification_uses_original_answer_when_process_dies_after_message_commit(
    notification_storage,
):
    storage, calls, _ = notification_storage
    session = await scheduled_session(storage)
    original = answer("Original scheduled answer")
    await EncryptedCredentialStorage.upsert_message(
        storage, session.user_id, session.id, original
    )
    await EncryptedCredentialStorage.upsert_message(
        storage, session.user_id, session.id, answer("Later followup")
    )
    await storage.recover_pending_notifications()
    assert calls[-1]["markdown"] == "Original scheduled answer"
    saved = await storage.get_session(session.user_id, session.agent_id, session.id)
    assert (
        saved.state.middle_context["schedule_notification"]["message_id"] == original.id
    )


async def test_notification_does_not_send_followup_when_original_result_is_delivered(
    notification_storage,
):
    storage, calls, _ = notification_storage
    session = await scheduled_session(storage)
    await storage.upsert_message(
        session.user_id, session.id, answer("Original scheduled answer")
    )
    await storage.upsert_message(session.user_id, session.id, answer("Later followup"))
    await storage.recover_pending_notifications()
    assert len(calls) == 1


async def test_notification_recovers_scope_failure_when_business_becomes_available(
    notification_storage,
):
    storage, calls, remote = notification_storage
    remote["scope_unavailable"] = True
    with pytest.raises(httpx.ConnectError):
        await scheduled_session(storage)
    remote["scope_unavailable"] = False
    await storage.recover_pending_notifications()
    assert calls[-1]["status"] == "failed"
    assert calls[-1]["markdown"] == ""
    assert "范围" in calls[-1]["error"]


async def test_notification_stops_retrying_when_schedule_was_deleted(
    notification_storage,
):
    storage, calls, remote = notification_storage
    session = await scheduled_session(storage)
    remote["unavailable"] = True
    await storage.upsert_message(
        session.user_id, session.id, answer("Original scheduled answer")
    )
    await storage.delete_schedule(session.user_id, session.source_schedule_id)
    remote["unavailable"] = False
    await storage.recover_pending_notifications()
    saved = await storage.get_session(session.user_id, session.agent_id, session.id)
    # AgentScope's real delete_schedule cascades the run sessions too.
    assert saved is None
    assert len(calls) == 1


async def test_notification_recovery_limits_work_when_many_runs_are_pending(
    notification_storage,
):
    storage, calls, _ = notification_storage
    for _ in range(3):
        session = await scheduled_session(storage)
        await EncryptedCredentialStorage.upsert_message(
            storage, session.user_id, session.id, answer("Original answer")
        )
    await storage.recover_pending_notifications(batch_size=2)
    assert len(calls) == 2
    await storage.recover_pending_notifications(batch_size=2)
    assert len(calls) == 3


async def test_notification_worker_restores_pending_delivery_when_process_restarts(
    notification_storage, monkeypatch
):
    storage, calls, remote = notification_storage
    session = await scheduled_session(storage)
    remote["unavailable"] = True
    await storage.upsert_message(session.user_id, session.id, answer("Original answer"))
    url = storage._url
    await storage.aclose()
    remote["unavailable"] = False
    remote["now"] += 20
    monkeypatch.setattr(type(storage), "_notification_loop", remote["loop"])
    async with type(storage)(
        url, key_provider=lambda: "a" * 64, create_tables=False, auto_migrate=True
    ) as restarted:
        await asyncio.wait_for(remote["delivered"].wait(), timeout=5)
        async with restarted._notification_lock(session.id):
            saved = await restarted.get_session(
                session.user_id, session.agent_id, session.id
            )
        assert (
            saved.state.middle_context["schedule_notification"]["status"] == "delivered"
        )
    assert len(calls) == 2
    assert calls[0] == calls[1]


async def test_notification_replays_same_result_when_process_loses_delivery_ack(
    notification_storage, monkeypatch
):
    storage, calls, _ = notification_storage
    session = await scheduled_session(storage)
    original = storage._write_marker

    async def unavailable_marker(record, marker):
        if marker["status"] == "delivered":
            raise RuntimeError("marker store unavailable")
        await original(record, marker)

    monkeypatch.setattr(storage, "_write_marker", unavailable_marker)
    await storage.upsert_message(session.user_id, session.id, answer("Original answer"))
    messages, _ = await storage.list_messages(session.user_id, session.id)
    assert messages[-1].finished_reason == ReplyFinishedReason.COMPLETED
    monkeypatch.setattr(storage, "_write_marker", original)
    await storage.recover_pending_notifications()
    assert len(calls) == 2
    assert calls[0] == calls[1]


async def test_notification_keeps_original_result_when_followup_finishes_during_outage(
    notification_storage,
):
    storage, calls, remote = notification_storage
    session = await scheduled_session(storage)
    remote["unavailable"] = True
    await storage.upsert_message(session.user_id, session.id, answer("Original answer"))
    await storage.upsert_message(session.user_id, session.id, answer("Followup answer"))
    remote["unavailable"] = False
    remote["now"] += 20
    await storage.recover_pending_notifications()
    assert calls[-1]["markdown"] == "Original answer"


async def test_notification_cancels_pending_marker_when_business_task_was_deleted(
    notification_storage,
):
    storage, calls, remote = notification_storage
    session = await scheduled_session(storage)
    remote["deleted"] = True
    await storage.upsert_message(session.user_id, session.id, answer("Original answer"))
    saved = await storage.get_session(session.user_id, session.agent_id, session.id)
    assert saved.state.middle_context["schedule_notification"]["status"] == "cancelled"
    await storage.recover_pending_notifications()
    assert len(calls) == 1


async def test_notification_marker_survives_when_config_update_uses_stale_state(
    notification_storage,
):
    storage, _, _ = notification_storage
    session = await scheduled_session(storage)
    await storage.upsert_message(session.user_id, session.id, answer("Original answer"))
    await storage.upsert_session(
        session.user_id,
        session.agent_id,
        session.config,
        state=AgentState(),
        session_id=session.id,
    )
    saved = await storage.get_session(session.user_id, session.agent_id, session.id)
    assert saved.state.middle_context["schedule_notification"]["status"] == "delivered"


async def test_notification_reports_failure_when_process_dies_before_scope_binding(
    notification_storage,
):
    storage, calls, _ = notification_storage
    session = await scheduled_session(storage)
    session.state.middle_context["schedule_notification"] = {
        "status": "binding",
        "message_id": None,
    }
    await EncryptedCredentialStorage.update_session_state(
        storage, session.user_id, session.agent_id, session.id, session.state
    )
    await storage.recover_pending_notifications()
    assert calls[-1]["status"] == "failed"
    assert calls[-1]["markdown"] == ""
    assert "范围" in calls[-1]["error"]


async def test_notification_reports_interruption_when_restart_loses_inflight_run(
    notification_storage,
):
    storage, calls, _ = notification_storage
    session = await scheduled_session(storage)
    await storage.aclose()
    async with type(storage)(
        storage._url,
        key_provider=lambda: "a" * 64,
        create_tables=False,
        auto_migrate=True,
    ) as restarted:
        await restarted.recover_pending_notifications()
        assert len(calls) == 1
        assert calls[0]["status"] == "failed"
        assert calls[0]["markdown"] == ""
        assert "服务已停止" in calls[0]["error"]
        saved = await restarted.get_session(
            session.user_id, session.agent_id, session.id
        )
        marker = saved.state.middle_context["schedule_notification"]
        message = await restarted.get_message(
            session.user_id, session.id, marker["message_id"]
        )
        assert message.finished_reason == ReplyFinishedReason.ERROR
        await restarted.upsert_message(
            session.user_id, session.id, answer("Followup answer")
        )
        await restarted.recover_pending_notifications()
        assert len(calls) == 1


async def test_notification_rejects_followup_result_when_restart_scan_has_not_run(
    notification_storage,
):
    storage, calls, _ = notification_storage
    session = await scheduled_session(storage)
    await storage.aclose()
    async with type(storage)(
        storage._url,
        key_provider=lambda: "a" * 64,
        create_tables=False,
        auto_migrate=True,
    ) as restarted:
        await restarted.upsert_message(
            session.user_id, session.id, answer("Followup answer")
        )
        assert len(calls) == 1
        assert calls[0]["status"] == "failed"
        assert calls[0]["markdown"] == ""
        assert "服务已停止" in calls[0]["error"]
        await restarted.recover_pending_notifications()
        assert len(calls) == 1


async def test_notification_restores_answer_when_restart_finds_committed_terminal(
    notification_storage,
):
    storage, calls, _ = notification_storage
    session = await scheduled_session(storage)
    await EncryptedCredentialStorage.upsert_message(
        storage, session.user_id, session.id, answer("Original committed answer")
    )
    await storage.aclose()
    async with type(storage)(
        storage._url,
        key_provider=lambda: "a" * 64,
        create_tables=False,
        auto_migrate=True,
    ) as restarted:
        await restarted.upsert_message(
            session.user_id, session.id, answer("Followup answer")
        )
        assert len(calls) == 1
        assert calls[0]["status"] == "success"
        assert calls[0]["markdown"] == "Original committed answer"
        await restarted.recover_pending_notifications()
        assert len(calls) == 1


async def test_notification_does_not_interrupt_run_when_current_process_is_active(
    notification_storage,
):
    storage, calls, _ = notification_storage
    session = await scheduled_session(storage)
    await storage.recover_pending_notifications()
    assert calls == []
    saved = await storage.get_session(session.user_id, session.agent_id, session.id)
    assert (
        saved.state.middle_context["schedule_notification"]["status"]
        == "awaiting_result"
    )
    await storage.upsert_message(
        session.user_id, session.id, answer("Current run answer")
    )
    assert len(calls) == 1
    assert calls[0]["status"] == "success"
    assert calls[0]["markdown"] == "Current run answer"
