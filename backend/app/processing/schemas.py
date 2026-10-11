from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.processing.domain import (
    IngestionJob,
    IngestionStage,
    IngestionStatus,
    StageStatus,
)


class IngestionStageRead(BaseModel):
    stage: IngestionStage
    status: StageStatus
    attempt: int
    error_code: str | None = None
    error_message: str | None = None
    progress: dict | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class IngestionJobRead(BaseModel):
    """A job as seen by one user; ``paper_id`` is that user's entry id."""

    id: UUID
    paper_id: UUID
    status: IngestionStatus
    current_stage: IngestionStage | None = None
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stages: list[IngestionStageRead]

    @classmethod
    def from_domain(
        cls, job: IngestionJob, *, user_paper_id: UUID
    ) -> "IngestionJobRead":
        return cls(
            id=job.id,
            paper_id=user_paper_id,
            status=job.status,
            current_stage=job.current_stage,
            error_code=job.error_code,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            stages=[
                IngestionStageRead(
                    stage=stage.stage,
                    status=stage.status,
                    attempt=stage.attempt,
                    error_code=stage.error_code,
                    error_message=stage.error_message,
                    progress=stage.progress,
                    started_at=stage.started_at,
                    finished_at=stage.finished_at,
                )
                for stage in job.stages
            ],
        )


class ProcessingRead(BaseModel):
    """Compact processing state used inside paper responses."""

    job_id: UUID | None = None
    status: IngestionStatus | None = None
    current_stage: IngestionStage | None = None
    error_code: str | None = None

    @classmethod
    def from_domain(cls, job: IngestionJob | None) -> "ProcessingRead":
        if job is None:
            return cls()
        return cls(
            job_id=job.id,
            status=job.status,
            current_stage=job.current_stage,
            error_code=job.error_code,
        )
