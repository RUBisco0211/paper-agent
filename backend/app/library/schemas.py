from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .domain import Capabilities
from .service import LibraryEntry


class CapabilitiesRead(BaseModel):
    """Capabilities of one entry; each one gates a different UI action."""

    has_source: bool
    has_metadata: bool
    has_parsed: bool
    has_index: bool
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
    added_at: datetime
    #: Projects this entry belongs to; empty when it is only in the library.
    project_ids: list[UUID] = Field(default_factory=list)
    capabilities: CapabilitiesRead
    #: How the paper's latest run is doing; ``None`` when it never ran.
    run_status: str | None = None


class UserPaperDetail(UserPaperSummary):
    abstract: str | None = None
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


class PaperMarkdownResponse(BaseModel):
    """The parsed full text, rendered as one markdown document."""

    markdown: str


class UploadResponse(BaseModel):
    """A stored file joins the paper's run; the entry appears once it succeeds."""

    run_id: UUID
    status: str


def _capabilities(capabilities: Capabilities) -> CapabilitiesRead:
    return CapabilitiesRead(
        has_source=capabilities.has_source,
        has_metadata=capabilities.has_metadata,
        has_parsed=capabilities.has_parsed,
        has_index=capabilities.has_index,
        has_embedding=capabilities.has_embedding,
    )


def to_summary(entry: LibraryEntry) -> UserPaperSummary:
    user_paper = entry.user_paper
    paper = entry.paper
    assert user_paper.created_at is not None
    return UserPaperSummary(
        id=user_paper.id,
        title=paper.title if paper else None,
        authors=paper.authors if paper else [],
        year=paper.year if paper else None,
        venue=paper.venue if paper else None,
        doi=paper.doi if paper else None,
        arxiv_id=paper.arxiv_id if paper else None,
        added_at=user_paper.created_at,
        project_ids=list(user_paper.project_ids),
        capabilities=_capabilities(entry.capabilities),
        run_status=(
            entry.latest_run.status.value if entry.latest_run else None
        ),
    )


def to_detail(entry: LibraryEntry) -> UserPaperDetail:
    summary = to_summary(entry)
    return UserPaperDetail(
        **summary.model_dump(),
        abstract=entry.paper.abstract if entry.paper else None,
        metadata=entry.paper.bibliographic if entry.paper else None,
        metadata_sources=entry.paper.metadata_sources if entry.paper else None,
        pdf=PdfInfoRead(
            available=entry.capabilities.has_source,
            page_count=entry.paper.page_count if entry.paper else None,
            byte_size=entry.paper.byte_size if entry.paper else None,
        ),
    )
