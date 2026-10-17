"""Recoverable schedule notifications at AgentScope's persistence boundary.

The scheduler persists a fresh session before enqueueing its wakeup. ChatService
persists terminal assistant messages, including setup failures, without requiring
a tool call. Only notification state and a message reference are stored here;
the answer stays in the framework's original message record.
"""

import asyncio
import logging
import time
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4
from weakref import WeakValueDictionary

import httpx
from agentscope.app.storage import SessionSource
from agentscope.app.storage._sql._tables import MessageRow, SessionRow
from agentscope.message import Msg
from agentscope.state import AgentState
from agentscope.types import ErrorInfo, ErrorType, ReplyFinishedReason
from sqlalchemy import or_, select

from .credential_storage import EncryptedCredentialStorage
from .tools.request import business_request
from .tools.scope import prepare_schedule_scope

logger = logging.getLogger(__name__)
_MARKER = "schedule_notification"
_FINISHED = {"delivered", "cancelled"}


def result_payload(msg: Msg) -> dict | None:
    if msg.role != "assistant" or msg.finished_reason is None:
        return None
    if msg.finished_reason == ReplyFinishedReason.COMPLETED:
        text = []
        for block in msg.content:
            if block.type in {"tool_call", "tool_result"}:
                text.clear()
            elif block.type == "text":
                text.append(block.text)
        return {"status": "success", "markdown": "\n".join(text), "error": None}
    errors = {
        "authentication": "模型凭据不可用，请在设置中检查凭据后重新运行。",
        "permission": "模型访问被拒绝，请检查模型权限后重新运行。",
        "rate_limit": "模型请求过于频繁或额度不足，请检查额度并稍后重新运行。",
        "setup": "任务未能启动，请检查模型配置与任务范围后重新运行。",
        "connection": "模型连接失败或超时，请稍后重新运行。",
    }
    error = errors.get(
        msg.error.type.value if msg.error else "",
        "任务运行失败，请稍后重新运行；如仍失败，请检查模型配置。",
    )
    if msg.finished_reason == ReplyFinishedReason.EXCEED_MAX_ITERS:
        error = "任务达到运行步数上限，请缩小任务范围后重新运行。"
    elif msg.finished_reason == ReplyFinishedReason.INTERRUPTED:
        error = "任务已停止，如需完整结果，请重新运行。"
    return {"status": "failed", "markdown": "", "error": error}


class ScheduleNotificationStorage(EncryptedCredentialStorage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._notification_task = None
        self._notification_locks = WeakValueDictionary()
        self._notification_cursor = ""
        self._notification_boot_id = None

    async def __aenter__(self):
        await super().__aenter__()
        self._notification_boot_id = uuid4().hex
        # Alembic's fileConfig can disable existing application loggers during
        # startup. Delivery failures must remain observable after migration.
        logger.disabled = False
        self._notification_task = asyncio.create_task(
            self._notification_loop(),
            name="schedule-notifications",
        )
        return self

    async def aclose(self):
        if self._notification_task is not None:
            self._notification_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._notification_task
            self._notification_task = None
        await super().aclose()

    def _notification_lock(self, session_id):
        lock = self._notification_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._notification_locks[session_id] = lock
        return lock

    async def _write_marker(self, record, marker):
        record.state.middle_context[_MARKER] = dict(marker)
        # Use the normal state API, but not our merge override: this write is
        # the authoritative notification transition, not a stale agent snapshot.
        await super().update_session_state(
            record.user_id,
            record.agent_id,
            record.id,
            record.state,
        )

    async def update_session_state(self, user_id, agent_id, session_id, state):
        async with self._notification_lock(session_id):
            saved = await self.get_session(user_id, agent_id, session_id)
            if saved is not None and _MARKER in saved.state.middle_context:
                state.middle_context[_MARKER] = dict(
                    saved.state.middle_context[_MARKER]
                )
            await super().update_session_state(user_id, agent_id, session_id, state)

    async def upsert_session(
        self,
        user_id,
        agent_id,
        config,
        state=None,
        session_id=None,
        source=SessionSource.USER,
        source_schedule_id=None,
        source_chat_id=None,
        source_channel_id=None,
    ):
        if source != SessionSource.SCHEDULE and session_id:
            async with self._notification_lock(session_id):
                saved = await self.get_session(user_id, agent_id, session_id)
                if (
                    state is not None
                    and saved is not None
                    and _MARKER in saved.state.middle_context
                ):
                    state = state.model_copy(deep=True)
                    state.middle_context[_MARKER] = dict(
                        saved.state.middle_context[_MARKER]
                    )
                return await super().upsert_session(
                    user_id,
                    agent_id,
                    config,
                    state,
                    session_id,
                    source,
                    source_schedule_id,
                    source_chat_id,
                    source_channel_id,
                )
        if source != SessionSource.SCHEDULE:
            return await super().upsert_session(
                user_id,
                agent_id,
                config,
                state,
                session_id,
                source,
                source_schedule_id,
                source_chat_id,
                source_channel_id,
            )
        session_id = session_id or uuid4().hex
        async with self._notification_lock(session_id):
            existing = await self.get_session(user_id, agent_id, session_id)
            state = (state or AgentState()).model_copy(deep=True)
            marker = (
                existing.state.middle_context.get(_MARKER) if existing else None
            ) or {
                "status": "binding",
                "message_id": None,
                "boot_id": self._notification_boot_id,
                "attempts": 0,
                "retry_at": 0,
            }
            state.middle_context[_MARKER] = dict(marker)
            record = await super().upsert_session(
                user_id,
                agent_id,
                config,
                state,
                session_id,
                source,
                source_schedule_id,
                source_chat_id,
                source_channel_id,
            )
            if marker["status"] == "binding":
                try:
                    await prepare_schedule_scope(self, user_id, agent_id, session_id)
                except Exception:
                    marker.update(
                        status="pending", message_id=uuid4().hex, scope_failure=True
                    )
                    await self._write_marker(record, marker)
                    await super().upsert_message(
                        user_id,
                        session_id,
                        self._lost_run_message(marker, scope_failure=True),
                    )
                    # No wakeup may be enqueued without a business scope. Recovery
                    # retries binding and notification only, never the Agent.
                    raise
                marker["status"] = "awaiting_result"
                await self._write_marker(record, marker)
            return record

    async def _first_terminal_message_id(self, session_id):
        # This is the AgentScope adapter's own database, not a business query.
        # Selecting only the original message ID avoids loading a long followup
        # history or copying result text into a second record.
        async with self._session() as session:
            return await session.scalar(
                select(MessageRow.msg_id)
                .where(
                    MessageRow.session_id == session_id,
                    MessageRow.payload["role"].as_string() == "assistant",
                    MessageRow.payload["finished_reason"].as_string().is_not(None),
                )
                .order_by(MessageRow.created_at, MessageRow.msg_id)
                .limit(1)
            )

    async def _reserve_result(self, record, marker, candidate_id=None):
        first = await self._first_terminal_message_id(record.id)
        if first is None and marker.get("boot_id") != self._notification_boot_id:
            # The in-memory wakeup/run belonged to a previous process. Reserve
            # its failure before a followup can become the first terminal reply.
            marker.update(status="pending", message_id=uuid4().hex, interrupted=True)
        else:
            if first is None and candidate_id is None:
                return False
            marker.update(status="pending", message_id=first or candidate_id)
        await self._write_marker(record, marker)
        return True

    async def upsert_message(self, user_id, session_id, msg):
        terminal = result_payload(msg) is not None
        async with self._notification_lock(session_id):
            if terminal:
                try:
                    record = await self.get_session(user_id, "", session_id)
                    if record is not None and record.source == SessionSource.SCHEDULE:
                        marker = dict(record.state.middle_context.get(_MARKER) or {})
                        if (
                            not marker.get("message_id")
                            and marker.get("status") not in _FINISHED
                        ):
                            await self._reserve_result(record, marker, msg.id)
                except Exception as exc:
                    self._log_failure(session_id, exc)
            await super().upsert_message(user_id, session_id, msg)
        if terminal:
            try:
                await self._deliver_pending(user_id, session_id)
            except Exception as exc:
                # The message is committed even when the marker store is down.
                # Recovery can rediscover its original ID after reconnection.
                self._log_failure(session_id, exc)

    @staticmethod
    def _lost_run_message(marker, *, scope_failure=False):
        error = (
            "任务范围绑定失败，请检查任务范围并重新运行。"
            if scope_failure
            else "任务运行期间服务已停止，请重新运行以获取完整结果。"
        )
        return Msg(
            id=marker["message_id"],
            name="Paper Agent",
            role="assistant",
            content=[],
            finished_reason=ReplyFinishedReason.ERROR,
            finished_at=datetime.now(UTC).isoformat(),
            error=ErrorInfo(type=ErrorType.SETUP, message=error),
        )

    async def _deliver_pending(self, user_id, session_id):
        async with self._notification_lock(session_id):
            record = await self.get_session(user_id, "", session_id)
            if record is None or record.source != SessionSource.SCHEDULE:
                return
            marker = dict(record.state.middle_context.get(_MARKER) or {})
            if marker.get("status") in _FINISHED:
                return
            if marker.get("retry_at", 0) > time.time():
                return
            try:
                schedule_id = record.source_schedule_id
                if not schedule_id:
                    marker["status"] = "cancelled"
                    await self._write_marker(record, marker)
                    return
                schedule = await self.get_schedule(user_id, schedule_id)
                if schedule is None:
                    marker["status"] = "cancelled"
                    await self._write_marker(record, marker)
                    return
                if marker.get("status") == "binding":
                    # A previous process persisted the session but never got as
                    # far as enqueueing the scheduler wakeup.
                    marker.update(
                        status="pending", message_id=uuid4().hex, scope_failure=True
                    )
                    await self._write_marker(record, marker)
                if not marker.get("message_id") and not await self._reserve_result(
                    record, marker
                ):
                    return
                msg = await self.get_message(user_id, session_id, marker["message_id"])
                if msg is None:
                    msg = self._lost_run_message(
                        marker, scope_failure=marker.get("scope_failure", False)
                    )
                    await super().upsert_message(user_id, session_id, msg)
                payload = result_payload(msg)
                if payload is None:
                    return
                if marker.get("scope_failure"):
                    await prepare_schedule_scope(
                        self, user_id, record.agent_id, session_id
                    )
                    payload["error"] = "任务范围绑定失败，请检查任务范围并重新运行。"
                elif marker.get("interrupted"):
                    payload["error"] = (
                        "任务运行期间服务已停止，请重新运行以获取完整结果。"
                    )
                response = await business_request(
                    "POST",
                    "schedule-results",
                    json={
                        "user_id": user_id,
                        "schedule_id": schedule_id,
                        "session_id": session_id,
                        "name": schedule.data.name,
                        **payload,
                    },
                )
                marker["status"] = (
                    "delivered" if response.get("notify_email", True) else "cancelled"
                )
                marker["retry_at"] = 0
                await self._write_marker(record, marker)
            except Exception as exc:
                if isinstance(
                    exc, httpx.HTTPStatusError
                ) and exc.response.status_code in {404, 410}:
                    marker["status"] = "cancelled"
                else:
                    marker["attempts"] = marker.get("attempts", 0) + 1
                    marker["retry_at"] = time.time() + min(
                        10 * 2 ** min(marker["attempts"] - 1, 6), 600
                    )
                await self._write_marker(record, marker)
                self._log_failure(session_id, exc)

    @staticmethod
    def _log_failure(session_id, exc):
        logger.error(
            "schedule_result_event_failed session_id=%s error_type=%s",
            session_id,
            type(exc).__name__,
        )

    async def recover_pending_notifications(self, *, batch_size=25):
        if not 1 <= batch_size <= 100:
            raise ValueError("Notification recovery batch must be between 1 and 100")
        marker = SessionRow.payload["state"]["middle_context"][_MARKER]
        status = marker["status"].as_string()
        retry_at = marker["retry_at"].as_float()
        async with self._session() as session:
            rows = (
                await session.execute(
                    select(SessionRow.id, SessionRow.user_id)
                    .where(
                        SessionRow.source == SessionSource.SCHEDULE,
                        SessionRow.id > self._notification_cursor,
                        or_(status.is_(None), status.not_in(_FINISHED)),
                        or_(retry_at.is_(None), retry_at <= time.time()),
                    )
                    .order_by(SessionRow.id)
                    .limit(batch_size)
                )
            ).all()
        if not rows:
            self._notification_cursor = ""
            return
        self._notification_cursor = rows[-1].id
        for row in rows:
            try:
                await self._deliver_pending(row.user_id, row.id)
            except Exception as exc:
                # Even a marker write failure is recoverable: the message and
                # prior marker remain durable and this scan wraps on next tick.
                self._log_failure(row.id, exc)

    async def _notification_loop(self):
        while True:
            try:
                await self.recover_pending_notifications()
            except Exception as exc:
                self._log_failure("recovery", exc)
            await asyncio.sleep(10)
