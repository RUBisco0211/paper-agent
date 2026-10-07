from uuid import UUID

import structlog

from ..library.domain import Paper
from ..library.repo import PaperRepository
from ..platform.errors import ConflictError, ErrorCode, NotFoundError
from .domain import ACTIVE_STATUSES, STAGE_ORDER, IngestionJob, IngestionStage
from .ports import IngestionJobRunner
from .repo import IngestionRepository

logger = structlog.get_logger(__name__)


class IngestionService:
    """Creates ingestion jobs and reports their stage state."""

    def __init__(
        self,
        repository: IngestionRepository,
        papers: PaperRepository,
        runner: IngestionJobRunner | None = None,
    ) -> None:
        self._repository = repository
        self._papers = papers
        self._runner = runner

    def user_paper_id(self, *, job_paper_id: UUID, user_id: UUID) -> UUID:
        """Map a shared paper to the requesting user's own entry id."""
        user_paper = self._papers.get_user_paper_for_paper(
            user_id=user_id,
            paper_id=job_paper_id,
        )
        if user_paper is None:
            # Same code as an unknown job: a job on another user's paper must not
            # reveal that the paper or the job exists.
            raise NotFoundError(
                "处理任务不存在",
                code=ErrorCode.INGESTION_JOB_NOT_FOUND,
            )
        return user_paper.id

    def start_for_paper(self, paper_id: UUID) -> IngestionJob | None:
        """Queue a job for the stages the paper still needs.

        Returns ``None`` when every stage already has verifiable output, so a
        duplicate upload never re-parses a paper that is already readable.
        """
        self._papers.lock_paper(paper_id)
        self._papers.expire_all()
        paper = self._papers.get_paper(paper_id)
        if paper is None:
            return None

        satisfied = _satisfied_stages(paper)
        if satisfied == set(STAGE_ORDER):
            return None

        active = self._repository.active_job_for_paper(paper_id)
        if active is not None:
            return active

        job = self._repository.create_job(paper_id=paper_id, stages=STAGE_ORDER)
        for stage in STAGE_ORDER:
            if stage in satisfied:
                self._repository.mark_stage_skipped(job.id, stage=stage)
        self._repository.commit()
        logger.info(
            "service.ingestion.queued",
            job_id=str(job.id),
            paper_id=str(paper_id),
            skipped=[stage.value for stage in sorted(satisfied)],
        )
        if self._runner is not None:
            self._runner.submit(job.id)
            # Give the caller the post-submit state rather than a stale row.
            self._repository.expire_all()
        return self._repository.get_job(job.id)

    def retry_job(self, job_id: UUID) -> IngestionJob:
        job = self._repository.get_job(job_id)
        if job is None:
            raise NotFoundError(
                "处理任务不存在",
                code=ErrorCode.INGESTION_JOB_NOT_FOUND,
            )
        if job.status in ACTIVE_STATUSES:
            raise ConflictError(
                "该处理任务仍在进行中",
                code=ErrorCode.INGESTION_ALREADY_RUNNING,
            )
        new_job = self.start_for_paper(job.paper_id)
        if new_job is None:
            raise ConflictError(
                "没有需要重试的处理阶段",
                code=ErrorCode.INGESTION_NOTHING_TO_RETRY,
            )
        logger.info(
            "service.ingestion.retried",
            previous_job_id=str(job_id),
            job_id=str(new_job.id),
        )
        return new_job

    def get_job(self, job_id: UUID) -> IngestionJob | None:
        return self._repository.get_job(job_id)

    def latest_job_for_paper(self, paper_id: UUID) -> IngestionJob | None:
        return self._repository.latest_job_for_paper(paper_id)

    def latest_jobs_for_papers(
        self,
        paper_ids: list[UUID],
    ) -> dict[UUID, IngestionJob]:
        return self._repository.latest_jobs_for_papers(paper_ids)

    def active_job_for_paper(self, paper_id: UUID) -> IngestionJob | None:
        return self._repository.active_job_for_paper(paper_id)


def _satisfied_stages(paper: Paper) -> set[IngestionStage]:
    """Stages whose artifacts already exist for this paper."""
    satisfied: set[IngestionStage] = set()
    if paper.has_metadata:
        satisfied.add(IngestionStage.METADATA)
    if paper.has_fulltext:
        satisfied.add(IngestionStage.FULLTEXT)
    if paper.has_keyword_index:
        satisfied.add(IngestionStage.CHUNKING)
    if paper.has_embedding:
        satisfied.add(IngestionStage.EMBEDDING)
    return satisfied
