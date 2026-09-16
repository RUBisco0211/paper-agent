from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ..library.schemas import UserPaperSummary


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProjectRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    paper_count: int
    created_at: datetime
    updated_at: datetime


class ProjectPapersAddRequest(BaseModel):
    paper_ids: list[UUID] = Field(min_length=1, max_length=100)


class ProjectPapersAddResponse(BaseModel):
    added: list[UserPaperSummary]
    already_present: list[UUID]
