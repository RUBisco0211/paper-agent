"""Identifier import: DOI/arXiv in, user library entry out."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ImportStatus(StrEnum):
    """Observable stages of one import request."""

    QUEUED = "queued"
    RESOLVING = "resolving"
    METADATA_READY = "metadata_ready"
    PDF_UNAVAILABLE = "pdf_unavailable"
    READY = "ready"
    FAILED = "failed"


TERMINAL_STATUSES = {
    ImportStatus.PDF_UNAVAILABLE,
    ImportStatus.READY,
    ImportStatus.FAILED,
}


@dataclass(frozen=True, slots=True)
class PaperImport:
    id: UUID
    user_id: UUID
    project_id: UUID | None
    user_paper_id: UUID | None
    identifier_type: str
    identifier: str
    status: ImportStatus
    error_code: str | None
    metadata_source: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
