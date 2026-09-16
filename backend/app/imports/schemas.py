from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ..scholar.identifiers import IdentifierType
from .domain import ImportStatus, PaperImport


class ImportRequest(BaseModel):
    identifier: str = Field(
        min_length=4,
        max_length=255,
        description="DOI、arXiv ID 或它们的规范链接",
    )
    project_id: UUID | None = None


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
