from uuid import UUID

from pydantic import BaseModel, Field

from .domain import ChannelStatus, SearchScope, SearchStatus


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


class DiscoveryRequest(BaseModel):
    user_id: UUID
    session_id: UUID
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=8, ge=1, le=10)


class DiscoveryResponse(BaseModel):
    papers: list[dict]


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


class BoundExcerptResponse(BaseModel):
    citation_id: str
    paper_id: UUID
    paper_title: str | None
    title_path: str | None
    snippet: str
    page_start: int | None
    page_end: int | None
    chunk_ids: list[UUID]
    source_locations: list[dict] = Field(default_factory=list)
