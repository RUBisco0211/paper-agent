from uuid import UUID

import structlog

from ..library.application import LibraryEntry, PaperLibraryService
from ..platform.errors import ErrorCode, NotFoundError
from ..projects.persistence import ProjectRepository
from .domain import (
    PendingMessage,
    Session,
    SessionEntry,
    normalize_title,
)
from .entries import DEFAULT_ENTRY_LIMIT, EntryStore
from .persistence import SessionRepository

logger = structlog.get_logger(__name__)


class SessionService:
    """Use cases for sessions, their scope and their entry history."""

    def __init__(
        self,
        repository: SessionRepository,
        entries: EntryStore,
        library: PaperLibraryService,
        projects: ProjectRepository,
    ) -> None:
        self._repository = repository
        self._entries = entries
        self._library = library
        self._projects = projects

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
