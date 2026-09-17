"""Generation lifecycle of one session.

Only one generation may run per session. A turn ends at a safe boundary: the
assistant entry is always written, pending input stays queued unless the turn
completed, and stopping never discards what was already generated.
"""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog

from ..platform.database import SessionFactory
from ..platform.errors import ErrorCode
from ..platform.tasks import TaskScheduler
from .agent import (
    AgentEventType,
    AgentRunner,
    AgentTurnRequest,
    LlmConfig,
    UnconfiguredAgentRunner,
)
from .context import project_messages
from .domain import (
    Delivery,
    EntryType,
    MessageRole,
    Session,
    SessionContext,
    StopReason,
)
from .entries import EntryStore
from .events import EventBroker
from .persistence import SessionRepository

logger = structlog.get_logger(__name__)


class _ActiveTurn:
    __slots__ = ("stop_requested",)

    def __init__(self) -> None:
        self.stop_requested = False


class SessionExecutor:
    """Runs the active generation of each session, one at a time."""

    def __init__(
        self,
        *,
        entries: EntryStore,
        events: EventBroker,
        session_factory: SessionFactory,
        scheduler: TaskScheduler,
        runner: AgentRunner | None = None,
    ) -> None:
        self._entries = entries
        self._events = events
        self._session_factory = session_factory
        self._scheduler = scheduler
        self._runner = runner or UnconfiguredAgentRunner()
        self._active: dict[UUID, _ActiveTurn] = {}

    @property
    def runner_name(self) -> str:
        return self._runner.name

    def is_active(self, session_id: UUID) -> bool:
        return session_id in self._active

    def start(
        self,
        *,
        session: Session,
        llm_config: LlmConfig,
    ) -> bool:
        """Begin a generation; returns False when one is already running."""
        if self.is_active(session.id):
            return False
        self._active[session.id] = _ActiveTurn()
        self._scheduler.submit(
            lambda: self._run(session=session, llm_config=llm_config),
            name=f"session-turn:{session.id}",
        )
        return True

    def request_stop(self, session_id: UUID) -> bool:
        turn = self._active.get(session_id)
        if turn is None:
            return False
        turn.stop_requested = True
        logger.info("session.executor.stop_requested", session_id=str(session_id))
        return True

    # Turn loop -------------------------------------------------------------
    async def _run(self, *, session: Session, llm_config: LlmConfig) -> None:
        turn = self._active[session.id]
        try:
            while True:
                delivered = await self._execute_turn(
                    session=session,
                    llm_config=llm_config,
                    turn=turn,
                )
                if delivered is None:
                    break
                # The queued message only becomes a user entry when it is
                # actually handed to the agent.
                self._entries.append_message(
                    user_id=session.user_id,
                    session_id=session.id,
                    role=MessageRole.USER,
                    content=delivered,
                )
                logger.info(
                    "session.executor.pending_delivered",
                    session_id=str(session.id),
                )
        finally:
            self._active.pop(session.id, None)

    async def _execute_turn(
        self,
        *,
        session: Session,
        llm_config: LlmConfig,
        turn: _ActiveTurn,
    ) -> str | None:
        session_id = session.id
        user_id = session.user_id
        self._events.publish(
            session_id=session_id,
            type=AgentEventType.STARTED.value,
            data={"provider": llm_config.provider, "model": llm_config.model},
        )
        entries = self._entries.list_entries(user_id=user_id, session_id=session_id)
        context = self._resolve_context(session)
        request = AgentTurnRequest(
            session_id=session_id,
            user_id=user_id,
            scope={
                "kind": context.kind,
                "project_id": str(context.project_id) if context.project_id else None,
                "paper_id": str(context.paper_id) if context.paper_id else None,
            },
            messages=project_messages(entries, context=context),
            llm_config=llm_config,
        )

        text_parts: list[str] = []
        stop_reason = StopReason.COMPLETED
        error_code: str | None = None
        usage: dict = {}
        try:
            async for event in self._runner.stream(request):
                if turn.stop_requested:
                    stop_reason = StopReason.ABORTED
                    break
                # Terminal runner events are not forwarded verbatim: the
                # executor publishes exactly one terminal event per turn,
                # carrying the entry id and the stop reason.
                if event.type is AgentEventType.STARTED:
                    continue
                if event.type is AgentEventType.COMPLETED:
                    usage = event.data or {}
                    stop_reason = StopReason.COMPLETED
                    continue
                if event.type is AgentEventType.FAILED:
                    stop_reason = StopReason.FAILED
                    error_code = str(
                        event.data.get("code") or ErrorCode.AGENT_UNAVAILABLE,
                    )
                    continue
                if event.type is AgentEventType.DELTA:
                    text_parts.append(str(event.data.get("text", "")))
                self._events.publish(
                    session_id=session_id,
                    type=event.type.value,
                    data=event.data,
                )
        except asyncio.CancelledError:
            stop_reason = StopReason.ABORTED
            raise
        except Exception as exc:  # unexpected runner failure
            logger.exception(
                "session.executor.crashed",
                session_id=str(session_id),
                error_type=type(exc).__name__,
            )
            stop_reason = StopReason.FAILED
            error_code = str(ErrorCode.INTERNAL_ERROR)

        self._finalize(
            session=session,
            llm_config=llm_config,
            text="".join(text_parts),
            stop_reason=stop_reason,
            error_code=error_code,
            usage=usage,
        )
        if stop_reason is not StopReason.COMPLETED:
            # Stopped or failed generations leave the queue for the user to
            # resume explicitly.
            self._publish_queue_state(session.id)
            return None
        return self._dequeue_next_pending(session.id)

    def _resolve_context(self, session: Session) -> SessionContext:
        if session.project_id is not None:
            return SessionContext(kind="project", project_id=session.project_id)
        return self._entries.session_context(
            user_id=session.user_id,
            session_id=session.id,
        )

    def _finalize(
        self,
        *,
        session: Session,
        llm_config: LlmConfig,
        text: str,
        stop_reason: StopReason,
        error_code: str | None,
        usage: dict | None = None,
    ) -> None:
        payload: dict = {
            "role": MessageRole.ASSISTANT.value,
            "content": text,
            "stop_reason": stop_reason.value,
            "provider": llm_config.provider,
            "model": llm_config.model,
        }
        if error_code:
            payload["error_code"] = error_code
        entry = self._entries.append(
            user_id=session.user_id,
            session_id=session.id,
            entry_type=EntryType.MESSAGE,
            payload=payload,
        )
        self._events.publish(
            session_id=session.id,
            type={
                StopReason.COMPLETED: AgentEventType.COMPLETED,
                StopReason.ABORTED: AgentEventType.ABORTED,
                StopReason.FAILED: AgentEventType.FAILED,
            }[stop_reason].value,
            data={
                "entry_id": str(entry.id),
                "sequence": entry.sequence,
                "stop_reason": stop_reason.value,
                "error_code": error_code,
                "content": text,
                "usage": usage or {},
            },
        )
        self._touch(session.id)

    # Queue -----------------------------------------------------------------
    def _dequeue_next_pending(self, session_id: UUID) -> str | None:
        """Deliver one pending message: steering first, then follow-up."""
        for delivery in (Delivery.STEERING, Delivery.FOLLOW_UP):
            content = self._dequeue_one(session_id=session_id, delivery=delivery)
            if content is not None:
                self._publish_queue_state(session_id)
                return content
        self._publish_queue_state(session_id)
        return None

    def _dequeue_one(self, *, session_id: UUID, delivery: Delivery) -> str | None:
        session = self._session_factory()
        try:
            repository = SessionRepository(session)
            pending = repository.dequeue_next(
                session_id=session_id,
                delivery=delivery,
            )
            session.commit()
            return pending.content if pending else None
        finally:
            session.close()

    def _publish_queue_state(self, session_id: UUID) -> None:
        session = self._session_factory()
        try:
            counts = SessionRepository(session).pending_counts([session_id])
            self._events.publish(
                session_id=session_id,
                type=AgentEventType.QUEUE_UPDATED.value,
                data=counts.get(session_id, {}),
            )
        finally:
            session.close()

    def _touch(self, session_id: UUID) -> None:
        session = self._session_factory()
        try:
            SessionRepository(session).touch(session_id, at=datetime.now(UTC))
            session.commit()
        except Exception as exc:  # pragma: no cover - activity stamp only
            logger.warning(
                "session.executor.touch_failed",
                session_id=str(session_id),
                error_type=type(exc).__name__,
            )
            session.rollback()
        finally:
            session.close()
