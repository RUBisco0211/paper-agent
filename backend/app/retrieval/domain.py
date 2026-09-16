"""Retrieval domain: evidence units, channels and fusion results."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SearchScope(StrEnum):
    """Authorized paper scope of a query."""

    LIBRARY = "library"
    PROJECT = "project"
    PAPER = "paper"


class SearchStatus(StrEnum):
    """Overall outcome of one search request."""

    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ChannelStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable evidence unit with its position in the original paper."""

    id: UUID
    paper_id: UUID
    chunk_index: int
    title_path: str | None
    content: str
    page_start: int | None
    page_end: int | None
    block_ids: list | None
    chunk_metadata: dict | None
    embedding_model: str | None
    embedding_dimensions: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """A chunk about to be stored; produced by the chunking stage."""

    chunk_index: int
    content: str
    title_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    block_ids: list | None = None
    chunk_metadata: dict | None = None


@dataclass(frozen=True, slots=True)
class ChunkMatch:
    """One channel hit for a chunk."""

    chunk: Chunk
    score: float
    rank: int
    channel: str


@dataclass(frozen=True, slots=True)
class Evidence:
    """Fused evidence returned to a caller or handed to the Agent."""

    paper_id: UUID
    chunk_ids: list[UUID]
    title_path: str | None
    snippet: str
    page_start: int | None
    page_end: int | None
    score: float
    chunk_index: int | None = None
    keyword_rank: int | None = None
    vector_rank: int | None = None

    def merged_with(self, other: "Evidence", *, max_chars: int) -> "Evidence":
        """Merge an adjacent chunk of the same paper into this evidence."""
        snippet = f"{self.snippet}\n{other.snippet}"
        return Evidence(
            paper_id=self.paper_id,
            chunk_ids=[*self.chunk_ids, *other.chunk_ids],
            title_path=self.title_path or other.title_path,
            snippet=snippet[:max_chars],
            page_start=self.page_start,
            page_end=other.page_end if other.page_end is not None else self.page_end,
            score=max(self.score, other.score),
            chunk_index=self.chunk_index,
            keyword_rank=_min_rank(self.keyword_rank, other.keyword_rank),
            vector_rank=_min_rank(self.vector_rank, other.vector_rank),
        )


@dataclass(frozen=True, slots=True)
class ChannelReport:
    channel: str
    status: ChannelStatus
    result_count: int
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    status: SearchStatus
    evidence: list[Evidence] = field(default_factory=list)
    channels: dict[str, ChannelReport] = field(default_factory=dict)


def _min_rank(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None
