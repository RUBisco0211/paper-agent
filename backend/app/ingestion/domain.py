"""Ingestion domain: processing stages, statuses and job state rules."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class IngestionStage(StrEnum):
    """Stages of turning a Paper into readable, searchable capabilities."""

    METADATA = "metadata"
    FULLTEXT = "fulltext"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"


STAGE_ORDER: tuple[IngestionStage, ...] = (
    IngestionStage.METADATA,
    IngestionStage.FULLTEXT,
    IngestionStage.CHUNKING,
    IngestionStage.EMBEDDING,
)


class IngestionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


TERMINAL_STATUSES = {IngestionStatus.SUCCEEDED, IngestionStatus.FAILED}
ACTIVE_STATUSES = {IngestionStatus.QUEUED, IngestionStatus.RUNNING}


@dataclass(frozen=True, slots=True)
class IngestionStageRecord:
    id: UUID
    stage: IngestionStage
    status: StageStatus
    attempt: int
    error_code: str | None
    error_message: str | None
    progress: dict | None
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class IngestionJob:
    id: UUID
    paper_id: UUID
    status: IngestionStatus
    current_stage: IngestionStage | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    stages: tuple[IngestionStageRecord, ...]

    def stage(self, stage: IngestionStage) -> IngestionStageRecord | None:
        return next((item for item in self.stages if item.stage == stage), None)

    @property
    def succeeded_stages(self) -> set[IngestionStage]:
        return {
            item.stage for item in self.stages if item.status is StageStatus.SUCCEEDED
        }
