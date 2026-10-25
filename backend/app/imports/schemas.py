from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .domain import ImportStage, ImportStageRecord, ImportStatus, PaperImport, StageStatus


class ImportRequest(BaseModel):
    identifier: str = Field(
        min_length=4,
        max_length=255,
        description="DOI、arXiv ID 或它们的规范链接",
    )


class ImportApprovalRequest(BaseModel):
    session_id: UUID
    candidate_tokens: list[str] = Field(min_length=1, max_length=10)


class ImportApprovalRead(BaseModel):
    id: UUID
    count: int


class ImportApprovalPreview(BaseModel):
    candidates: list[dict]


class BoundBatchImportRequest(BaseModel):
    user_id: UUID
    session_id: UUID


class BatchImportRead(BaseModel):
    results: list[dict]


class ImportStageRead(BaseModel):
    """One stage of an import, in the order the interface shows it."""

    stage: ImportStage
    status: StageStatus
    attempt: int = 0
    error_code: str | None = None
    error_message: str | None = None
    progress: dict | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def from_domain(cls, record: ImportStageRecord) -> "ImportStageRead":
        return cls(
            stage=record.stage,
            status=record.status,
            attempt=record.attempt,
            error_code=record.error_code,
            error_message=record.error_message,
            progress=record.progress,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )


class ImportQueueItem(BaseModel):
    id: str
    identifier: str
    identifier_type: str
    title: str | None = None
    paper_id: str | None = None
    status: str
    stage: str | None = None
    created_at: datetime
    error_code: str | None = None
    stages: list[ImportStageRead] = Field(default_factory=list)


class ImportQueueRead(BaseModel):
    items: list[ImportQueueItem]


class DiscoveryRequest(BaseModel):
    user_id: UUID
    session_id: UUID
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=8, ge=1, le=10)


class ManualDiscoveryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=10, ge=1, le=20)


class DiscoveryResponse(BaseModel):
    papers: list[dict]
    failed_sources: list[str] = Field(default_factory=list)


class ImportRead(BaseModel):
    """One import: which paper it produced and how far its stages got."""

    id: UUID
    status: ImportStatus
    #: ``doi``, ``arxiv`` or ``upload`` — an import can start without either.
    identifier_type: str
    identifier: str
    paper_id: UUID | None = None
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stages: list[ImportStageRead] = Field(default_factory=list)

    @classmethod
    def from_domain(
        cls,
        record: PaperImport,
        *,
        user_paper_id: UUID | None = None,
    ) -> "ImportRead":
        return cls(
            id=record.id,
            status=record.status,
            identifier_type=record.identifier_type,
            identifier=record.identifier,
            # The user's entry, which only exists once the import finished.
            paper_id=user_paper_id,
            error_code=record.error_code,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            stages=[ImportStageRead.from_domain(stage) for stage in record.stages],
        )
