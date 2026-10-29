from uuid import UUID

from pydantic import BaseModel, Field

from .domain import ChannelStatus, SearchScope, SearchStatus


class QuoteReferenceResolveRequest(BaseModel):
    user_id: UUID
    session_id: UUID
    kind: str
    user_paper_id: UUID
    # ``kind="paper"`` only needs the entry: the other kinds locate a fragment.
    version: str | None = None
    page: int | None = Field(default=None, ge=1)
    block_id: int | None = None
    start: int | None = None
    end: int | None = None
    rects: list[list[float]] = Field(default_factory=list)
    selected_text: str = Field(max_length=2000)
    comment: str = Field(max_length=2000)
    include_image: bool = False


class QuoteReferenceResolved(BaseModel):
    title: str | None
    page: int | None = None
    has_fulltext: bool | None = None
    image_base64: str | None = None
    image_media_type: str | None = None


class PaperPageRequest(BaseModel):
    user_id: UUID
    session_id: UUID
    paper_id: UUID
    page: int = Field(ge=1)


class PageImageRead(BaseModel):
    block_id: int
    caption: str | None = None


class PaperPageRead(BaseModel):
    title: str | None
    page: int
    total_pages: int
    markdown: str
    images: list[PageImageRead]
    truncated: bool
    partial_block_id: int | None = None
    omitted_block_ids: list[int]


class PaperImageRequest(BaseModel):
    user_id: UUID
    session_id: UUID
    paper_id: UUID
    block_id: int = Field(ge=0)


class PaperImageRead(BaseModel):
    title: str | None
    page: int
    caption: str | None = None
    image_base64: str
    image_media_type: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    scope: SearchScope = SearchScope.LIBRARY
    project_id: UUID | None = None
    paper_ids: list[UUID] | None = Field(
        default=None,
        description="user paper ids；scope=paper 时必填",
    )
    limit: int = Field(default=10, ge=1, le=50)


class ChannelRead(BaseModel):
    status: ChannelStatus
    result_count: int
    detail: str | None = None


class EvidenceRead(BaseModel):
    paper_id: UUID
    chunk_ids: list[UUID]
    title_path: str | None = None
    snippet: str
    page_start: int | None = None
    page_end: int | None = None
    score: float
    keyword_rank: int | None = None
    vector_rank: int | None = None


class SearchResponse(BaseModel):
    query: str
    scope: SearchScope
    status: SearchStatus
    channels: dict[str, ChannelRead]
    evidence: list[EvidenceRead]


class BoundSearchRequest(BaseModel):
    user_id: UUID
    session_id: UUID
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)


class BoundEvidenceRead(EvidenceRead):
    citation_id: str


class BoundSearchResponse(BaseModel):
    scope: SearchScope
    status: SearchStatus
    channels: dict[str, ChannelRead]
    evidence: list[BoundEvidenceRead]


class BoundListResponse(BaseModel):
    scope: SearchScope
    total: int
    papers: list[dict]
