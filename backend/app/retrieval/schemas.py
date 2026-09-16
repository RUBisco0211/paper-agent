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
