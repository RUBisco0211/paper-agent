from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.literature_support.scholar.identifiers import IdentifierType

from .domain import ImportStatus, PaperImport


class ImportRequest(BaseModel):
    identifier: str = Field(
        min_length=4,
        max_length=255,
        description="DOI、arXiv ID 或它们的规范链接",
    )
    project_id: UUID | None = None


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


class ImportQueueItem(BaseModel):
    id: str
    kind: str
    identifier: str | None = None
    title: str | None = None
    paper_id: str | None = None
    status: str
    stage: str | None = None
    created_at: datetime
    error_code: str | None = None


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
    """Import progress; ``paper_id`` is the user's own entry id."""

    id: UUID
    status: ImportStatus
    identifier_type: IdentifierType
    identifier: str
    paper_id: UUID | None = None
    project_id: UUID | None = None
    metadata_source: str | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None

    @classmethod
    def from_domain(cls, record: PaperImport) -> "ImportRead":
        return cls(
            id=record.id,
            status=record.status,
            identifier_type=IdentifierType(record.identifier_type),
            identifier=record.identifier,
            paper_id=record.user_paper_id,
            project_id=record.project_id,
            metadata_source=record.metadata_source,
            error_code=record.error_code,
            created_at=record.created_at,
            updated_at=record.updated_at,
            finished_at=record.finished_at,
        )
