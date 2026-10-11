from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.processing.schemas import IngestionJobRead, ProcessingRead

from .domain import Capabilities, MetadataStatus, PaperSource
from .service import LibraryEntry


class CapabilitiesRead(BaseModel):
    """Capabilities of one entry; each one gates a different UI action."""

    has_pdf: bool
    has_metadata: bool
    has_fulltext: bool
    has_keyword_index: bool
    has_embedding: bool


class PdfInfoRead(BaseModel):
    available: bool
    page_count: int | None = None
    byte_size: int | None = None


class UserPaperSummary(BaseModel):
    id: UUID
    title: str | None
    authors: list[str]
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    source: PaperSource
    original_filename: str | None = None
    added_at: datetime
    capabilities: CapabilitiesRead
    processing: ProcessingRead


class UserPaperDetail(UserPaperSummary):
    abstract: str | None = None
    metadata_status: MetadataStatus
    metadata: dict | None = None
    metadata_sources: list | None = None
    pdf: PdfInfoRead
    pdf_version: str | None = None
    artifact_version: str | None = None


class PaperBlockRead(BaseModel):
    id: int
    type: str
    page: int
    text: str
    formula: str | None = None
    has_image: bool = False
    bbox: list[float] | None = None
    page_size: list[float] | None = None
    coordinate_system: str | None = None


class PaperBlocksResponse(BaseModel):
    types: list[str]
    items: list[PaperBlockRead]
    total: int
    offset: int
    limit: int


class UploadResponse(BaseModel):
    paper: UserPaperSummary
    ingestion_job: IngestionJobRead | None = None


class PaperInfoUpdateRequest(BaseModel):
    """用户可以编辑的书目信息字段（界面「编辑信息」）。"""

    title: str | None = Field(default=None, min_length=1, max_length=512)
    authors: list[str] | None = None
    abstract: str | None = None
    doi: str | None = Field(default=None, max_length=255)
    arxiv_id: str | None = Field(default=None, max_length=64)
    year: int | None = Field(default=None, ge=1500, le=2100)
    venue: str | None = Field(default=None, max_length=255)


class MetadataFetchRead(BaseModel):
    """一次「获取元数据」的结果，包含失败原因（界面「获取元数据」）。"""

    status: MetadataStatus
    source: str | None = None
    error_code: str | None = None
    applied_fields: list[str] = []


class FetchPdfResponse(UploadResponse):
    metadata: MetadataFetchRead


class FetchMetadataResponse(BaseModel):
    paper: UserPaperDetail
    metadata: MetadataFetchRead


def _capabilities(capabilities: Capabilities) -> CapabilitiesRead:
    return CapabilitiesRead(
        has_pdf=capabilities.has_pdf,
        has_metadata=capabilities.has_metadata,
        has_fulltext=capabilities.has_fulltext,
        has_keyword_index=capabilities.has_keyword_index,
        has_embedding=capabilities.has_embedding,
    )


def to_summary(entry: LibraryEntry) -> UserPaperSummary:
    user_paper = entry.user_paper
    assert user_paper.created_at is not None
    return UserPaperSummary(
        id=user_paper.id,
        title=user_paper.title,
        authors=user_paper.authors,
        year=user_paper.year,
        venue=user_paper.venue,
        doi=user_paper.doi,
        arxiv_id=user_paper.arxiv_id,
        source=user_paper.source,
        original_filename=user_paper.original_filename,
        added_at=user_paper.created_at,
        capabilities=_capabilities(entry.capabilities),
        processing=ProcessingRead.from_domain(entry.latest_job),
    )


def to_detail(entry: LibraryEntry) -> UserPaperDetail:
    summary = to_summary(entry)
    return UserPaperDetail(
        **summary.model_dump(),
        abstract=entry.user_paper.abstract,
        metadata_status=entry.user_paper.metadata_status,
        metadata=entry.user_paper.bibliographic,
        metadata_sources=entry.user_paper.metadata_sources,
        pdf=PdfInfoRead(
            available=entry.capabilities.has_pdf,
            page_count=entry.paper.page_count if entry.paper else None,
            byte_size=entry.paper.byte_size if entry.paper else None,
        ),
    )
