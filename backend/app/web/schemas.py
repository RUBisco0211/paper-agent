"""Request shapes for the internal web endpoints used by the agent service."""

from uuid import UUID

from pydantic import BaseModel, Field


class WebSearchRequest(BaseModel):
    user_id: UUID
    query: str = Field(min_length=1, max_length=2000)
    max_results: int = Field(default=5, ge=1, le=10)


class WebFetchRequest(BaseModel):
    user_id: UUID
    url: str = Field(min_length=1, max_length=2048)
    offset: int = Field(default=0, ge=0)
    max_chars: int = Field(default=8000, ge=1, le=20000)


class WebExcerptRequest(BaseModel):
    user_id: UUID
    url: str = Field(min_length=1, max_length=2048)
    query: str = Field(min_length=1, max_length=2000)
    chunks: int = Field(default=3, ge=1, le=5)
