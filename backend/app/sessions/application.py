from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog

from ..library.application import LibraryEntry, PaperLibraryService
from ..platform.errors import ConflictError, ErrorCode, NotFoundError, ValidationError
from ..projects.persistence import ProjectRepository
from .agent import AgentEventType, LlmConfig
from .domain import (
    Delivery,
    MessageRole,
    PendingMessage,
    Session,
    SessionEntry,
    normalize_message,
    normalize_title,
)
from .entries import DEFAULT_ENTRY_LIMIT, EntryStore
from .events import EventBroker, SessionEvent
from .executor import SessionExecutor
from .persistence import SessionRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MessageSubmission:
    """Outcome of submitting user input to a session."""

    entry: SessionEntry | None = None
    pending: PendingMessage | None = None
    generation_started: bool = False


@dataclass(frozen=True, slots=True)
class ResumeOutcome:
    delivered: SessionEntry | None
    remaining: dict[str, int]


class SessionService:
    """Use cases for sessions, their scope and their entry history."""

    def __init__(
        self,
        repository: SessionRepository,
        entries: EntryStore,
        library: PaperLibraryService,
        projects: ProjectRepository,
        executor: SessionExecutor,
        events: EventBroker,
    ) -> None:
        self._repository = repository
        self._entries = entries
        self._library = library
        self._projects = projects
        self._executor = executor
        self._events = events

    # Sessions --------------------------------------------------------------
    def create(
        self,
        *,
        user_id: UUID,
        title: str | None = None,
        project_id: UUID | None = None,
    ) -> Session:
        if project_id is not None:
            project = self._projects.get_project(project_id)
            if project is None or project.user_id != user_id:
                raise NotFoundError("项目不存在", code=ErrorCode.PROJECT_NOT_FOUND)
        session = self._repository.add_session(
            user_id=user_id,
            project_id=project_id,
            title=normalize_title(title) if title else None,
        )
        self._repository.commit()
        logger.info(
            "service.session.created",
            session_id=str(session.id),
            scope=session.scope,
        )
        return session

    def list_sessions(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        project_id: UUID | None = None,
        library_only: bool = False,
    ) -> tuple[list[tuple[Session, dict[str, int]]], int]:
        sessions, total = self._repository.list_sessions(
            user_id=user_id,
            limit=limit,
            offset=offset,
            project_id=project_id,
            library_only=library_only,
        )
        counts = self._repository.pending_counts([session.id for session in sessions])
        return [(session, counts.get(session.id, {})) for session in sessions], total

    def get(self, *, user_id: UUID, session_id: UUID) -> Session:
        session = self._repository.get_session(session_id)
        if session is None or session.user_id != user_id:
            # Another user's session id must not be distinguishable from a
            # non-existent one.
            raise NotFoundError("会话不存在", code=ErrorCode.SESSION_NOT_FOUND)
        return session

    def rename(self, *, user_id: UUID, session_id: UUID, title: str) -> Session:
        self.get(user_id=user_id, session_id=session_id)
        updated = self._repository.update_session(
            session_id,
            title=normalize_title(title),
        )
        assert updated is not None
        self._repository.commit()
        return updated

    def delete(self, *, user_id: UUID, session_id: UUID) -> None:
        """Delete a session, its pending input, citations and entry log."""
        self.get(user_id=user_id, session_id=session_id)
        self._repository.delete_session(session_id)
        self._repository.commit()
        self._entries.purge(user_id=user_id, session_id=session_id)
        logger.info("service.session.deleted", session_id=str(session_id))

    # History ---------------------------------------------------------------
    def list_entries(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        after_sequence: int = 0,
        limit: int = DEFAULT_ENTRY_LIMIT,
    ) -> tuple[Session, list[SessionEntry]]:
        session = self.get(user_id=user_id, session_id=session_id)
        entries = self._entries.list_entries(
            user_id=user_id,
            session_id=session_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        return session, entries

    def pending_snapshot(self, session_id: UUID) -> list[PendingMessage]:
        return self._repository.list_pending(session_id)

    # Messages and generation -----------------------------------------------
    def submit_message(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        content: str,
        delivery: Delivery | None = None,
        llm_config: LlmConfig | None = None,
    ) -> MessageSubmission:
        """Accept user input: run it now, or queue it behind the active turn."""
        message = normalize_message(content)
        session = self.get(user_id=user_id, session_id=session_id)

        if self._executor.is_active(session_id):
            # A running generation answers on its own schedule; the new input
            # waits in the queue it was assigned to.
            pending = self._repository.enqueue(
                session_id=session_id,
                delivery=delivery or Delivery.FOLLOW_UP,
                content=message,
            )
            self._repository.commit()
            self._publish_queue_state(session_id)
            logger.info(
                "service.session.message_queued",
                session_id=str(session_id),
                delivery=pending.delivery.value,
            )
            return MessageSubmission(pending=pending)

        if llm_config is None:
            raise ValidationError("空闲会话提交消息时需要在请求体中提供 llm_config")

        entry = self._entries.append_message(
            user_id=user_id,
            session_id=session_id,
            role=MessageRole.USER,
            content=message,
        )
        self._repository.touch(session_id, at=datetime.now(UTC))
        self._repository.commit()
        started = self._executor.start(session=session, llm_config=llm_config)
        self._publish_queue_state(session_id)
        logger.info(
            "service.session.message_submitted",
            session_id=str(session_id),
            generation_started=started,
        )
        return MessageSubmission(entry=entry, generation_started=started)

    def stop(self, *, user_id: UUID, session_id: UUID) -> None:
        self.get(user_id=user_id, session_id=session_id)
        if not self._executor.request_stop(session_id):
            raise ConflictError(
                "当前没有进行中的生成",
                code=ErrorCode.SESSION_NOT_GENERATING,
            )

    def resume(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        llm_config: LlmConfig,
    ) -> ResumeOutcome:
        """Deliver the next queued message after a stop, failure or restart."""
        session = self.get(user_id=user_id, session_id=session_id)
        if self._executor.is_active(session_id):
            raise ConflictError(
                "该会话已经在生成中",
                code=ErrorCode.SESSION_BUSY,
            )
        pending = self._repository.list_pending(session_id)
        if not pending:
            raise ConflictError(
                "没有待投递消息",
                code=ErrorCode.PENDING_MESSAGE_NOT_FOUND,
            )

        delivered: SessionEntry | None = None
        for delivery in (Delivery.STEERING, Delivery.FOLLOW_UP):
            item = self._repository.dequeue_next(
                session_id=session_id,
                delivery=delivery,
            )
            if item is None:
                continue
            delivered = self._entries.append_message(
                user_id=user_id,
                session_id=session_id,
                role=MessageRole.USER,
                content=item.content,
            )
            break
        self._repository.touch(session_id, at=datetime.now(UTC))
        self._repository.commit()
        assert delivered is not None
        self._executor.start(session=session, llm_config=llm_config)
        remaining = self._repository.pending_counts([session_id]).get(session_id, {})
        self._publish_queue_state(session_id)
        logger.info("service.session.resumed", session_id=str(session_id))
        return ResumeOutcome(delivered=delivered, remaining=remaining)

    def replay_events(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        after_sequence: int = 0,
    ) -> list[SessionEvent]:
        self.get(user_id=user_id, session_id=session_id)
        return self._events.replay(session_id, after_sequence=after_sequence)

    def event_stream(
        self,
        *,
        session_id: UUID,
        after_sequence: int,
        idle_timeout_seconds: float,
    ):
        return self._events.subscribe(
            session_id,
            after_sequence=after_sequence,
            idle_timeout_seconds=idle_timeout_seconds,
        )

    def is_generating(self, session_id: UUID) -> bool:
        return self._executor.is_active(session_id)

    def _publish_queue_state(self, session_id: UUID) -> None:
        counts = self._repository.pending_counts([session_id]).get(session_id, {})
        self._events.publish(
            session_id=session_id,
            type=AgentEventType.QUEUE_UPDATED.value,
            data={
                "steering": counts.get("steering", 0),
                "follow_up": counts.get("follow_up", 0),
            },
        )

    # Scope -----------------------------------------------------------------
    def scope_entries(self, session: Session) -> list[LibraryEntry]:
        """Papers the agent of this session is allowed to read."""
        if session.project_id is None:
            return self._library.list_entries(
                user_id=session.user_id,
                limit=200,
                offset=0,
            )[0]
        member_ids = list(self._projects.paper_ids_of(session.project_id))
        return self._library.entries_for(
            user_id=session.user_id,
            user_paper_ids=member_ids,
        )


class ProjectSessionPurger:
    """Implements the projects module's cleanup boundary."""

    def __init__(self, repository: SessionRepository, entries: EntryStore) -> None:
        self._repository = repository
        self._entries = entries

    def purge_project_sessions(self, *, user_id: UUID, project_id: UUID) -> int:
        sessions = self._repository.list_sessions_of_project(
            user_id=user_id,
            project_id=project_id,
        )
        for session in sessions:
            self._entries.purge(user_id=user_id, session_id=session.id)
        logger.info(
            "service.session.project_purged",
            project_id=str(project_id),
            purged=len(sessions),
        )
        return len(sessions)
