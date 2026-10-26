"""Attach a user to a paper's processing, or start one when none is active.

This is the single place where two users asking for the same paper stop forking:
an active run accepts more users instead of being duplicated, so a paper is
processed once no matter how many people want it.
"""

from uuid import UUID

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..library.repo import PaperRepository
from ..platform.database import SessionFactory
from .domain import Run, RunStatus
from .repo import RunRepository

logger = structlog.get_logger(__name__)

#: Statuses of a run that still owes its users a result.
ACTIVE = ("pending", "running")


class RunService:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def request(self, *, user_id: UUID, paper_id: UUID) -> Run:
        """Give this user the paper's run, reusing an active one if any.

        A paper that already succeeded has nothing left to do, so the caller's
        entry is written at once instead of leaving them waiting on a finished
        run.
        """
        session = self._session_factory()
        try:
            runs = RunRepository(session)
            run = runs.active_for_paper(paper_id)
            if run is None:
                finished = runs.latest_for_paper(paper_id)
                if finished is not None and finished.status is RunStatus.SUCCESS:
                    PaperRepository(session).link_paper(
                        user_id=user_id, paper_id=paper_id
                    )
                    session.commit()
                    logger.info(
                        "pipelines.request.satisfied",
                        paper_id=str(paper_id),
                        run_id=str(finished.id),
                        user_id=str(user_id),
                    )
                    return finished
                run = self._start(session, runs, paper_id)
            runs.add_user(user_id=user_id, run=run)
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

    def _start(self, session: Session, runs: RunRepository, paper_id: UUID) -> Run:
        """Create the active run, tolerating a concurrent starter.

        The partial unique index is the arbiter: whoever loses the race reads
        the winner's row instead of creating a second active run.
        """
        try:
            run = runs.add(paper_id)
            session.commit()
            logger.info(
                "pipelines.request.started",
                paper_id=str(paper_id),
                run_id=str(run.id),
            )
            return run
        except IntegrityError:
            session.rollback()
            existing = runs.active_for_paper(paper_id)
            if existing is None:  # pragma: no cover - index released meanwhile
                raise
            return existing

    def latest_for_papers(self, paper_ids: list[UUID]) -> dict[UUID, Run]:
        """The most recent run of each paper, whoever asked for it."""
        if not paper_ids:
            return {}
        session = self._session_factory()
        try:
            return RunRepository(session).latest_for_papers(paper_ids)
        finally:
            session.close()

    def ensure_entry(self, *, user_id: UUID, paper_id: UUID) -> None:
        """Give a user their library entry for a paper that is already usable."""
        session = self._session_factory()
        try:
            papers = PaperRepository(session)
            if papers.get_user_paper_for_paper(
                user_id=user_id, paper_id=paper_id
            ) is not None:
                return
            papers.add_user_paper(user_id=user_id, paper_id=paper_id)
            session.commit()
        finally:
            session.close()
