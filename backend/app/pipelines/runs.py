"""Attach a user to a paper's processing, or start one when none is active.

This is the single place where two users asking for the same paper stop forking:
an active run accepts more users instead of being duplicated, so a paper is
processed once no matter how many people want it.
"""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..library.repo import PaperRepository
from ..platform.database import SessionFactory
from ..platform.errors import ErrorCode, NotFoundError
from ..projects.repo import ProjectRecord, ProjectRepository
from .domain import Run, RunStatus
from .repo import RunRepository, UserRunRequest

logger = structlog.get_logger(__name__)


class RunService:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def request(
        self,
        *,
        user_id: UUID,
        paper_id: UUID,
        project_id: UUID | None = None,
    ) -> Run:
        """Give this user the paper's run and file the result where asked.

        A paper that already succeeded has nothing left to do, so no request
        row is written and the entry appears at once: there is no progress to
        watch, and the queue only speaks for work still owed.
        """
        session = self._session_factory()
        try:
            if project_id is not None:
                self._require_own_project(
                    session, user_id=user_id, project_id=project_id
                )
            runs = RunRepository(session)
            papers = PaperRepository(session)
            # The finisher takes the same lock before publishing success and
            # granting entries. No request can join after its audience is read.
            papers.lock_paper(paper_id)
            run = runs.active_for_paper(paper_id)
            if run is None:
                finished = runs.latest_for_paper(paper_id)
                if finished is not None and finished.status is RunStatus.SUCCESS:
                    # Nothing is being waited on, so no request row: the user
                    # simply owns the paper from now on.
                    entry = papers.link_paper(user_id=user_id, paper_id=paper_id)
                    self._file_into_project(
                        session, project_id=project_id, user_paper_id=entry.id
                    )
                    session.commit()
                    logger.info(
                        "pipelines.request.satisfied",
                        paper_id=str(paper_id),
                        run_id=str(finished.id),
                        user_id=str(user_id),
                    )
                    return finished
                run = runs.add(paper_id)
            runs.add_user(user_id=user_id, run=run, project_id=project_id)
            session.commit()
            logger.info(
                "pipelines.request.attached",
                paper_id=str(paper_id),
                run_id=str(run.id),
                user_id=str(user_id),
            )
            return run
        finally:
            session.close()

    # Requests --------------------------------------------------------------
    def requests_of_run(self, run_id: UUID) -> list[UserRunRequest]:
        """Everyone waiting on this run, with the project each asked for."""
        session = self._session_factory()
        try:
            return RunRepository(session).requests_of_run(run_id)
        finally:
            session.close()

    def latest_for_papers(self, paper_ids: list[UUID]) -> dict[UUID, Run]:
        """The most recent run of each paper, whoever asked for it."""
        if not paper_ids:
            return {}
        session = self._session_factory()
        try:
            return RunRepository(session).latest_for_papers(paper_ids)
        finally:
            session.close()

    def list_requests(self, *, user_id: UUID, limit: int) -> list[UserRunRequest]:
        session = self._session_factory()
        try:
            return RunRepository(session).list_requests_for_user(
                user_id=user_id, limit=limit
            )
        finally:
            session.close()

    # Internals -------------------------------------------------------------
    @staticmethod
    def _require_own_project(
        session: Session, *, user_id: UUID, project_id: UUID
    ) -> None:
        """A request may only name a project the user owns."""
        owned = session.scalar(
            select(ProjectRecord.id)
            .where(ProjectRecord.id == project_id)
            .where(ProjectRecord.user_id == user_id)
        )
        if owned is None:
            raise NotFoundError("项目不存在", code=ErrorCode.PROJECT_NOT_FOUND)

    @staticmethod
    def _file_into_project(
        session: Session, *, project_id: UUID | None, user_paper_id: UUID
    ) -> None:
        """Put the new entry into the project named by the request, if any."""
        if project_id is None:
            return
        ProjectRepository(session).add_papers(
            project_id=project_id, user_paper_ids=[user_paper_id]
        )
