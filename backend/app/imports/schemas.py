from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    identifier: str = Field(
        min_length=4,
        max_length=255,
        description="DOI、arXiv ID 或它们的规范链接",
    )
    #: Also file the paper into this project once it is usable.
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


class QueueRunRead(BaseModel):
    """The processing run a download joined, as the queue shows it."""

    status: str
    stage: str | None = None
    error_message: str | None = None


class DownloadQueueItem(BaseModel):
    """One request the user made: fetching a file, then processing it.

    ``source`` says whether the request carried a download (``download``) or
    arrived with its file in hand (``request``); the list view does not have to
    tell them apart, but the detail view lists the steps each one actually had.
    """

    source: str
    id: str
    identifier: str
    identifier_type: str
    status: str
    paper_id: str | None = None
    run_id: str | None = None
    project_id: str | None = None
    source_url: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    run: QueueRunRead | None = None


class ImportQueueRead(BaseModel):
    items: list[DownloadQueueItem]


class DownloadRead(BaseModel):
    """The request just queued; processing happens in the background."""

    id: UUID
    identifier_type: str
    identifier: str
    status: str
    created_at: datetime


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
