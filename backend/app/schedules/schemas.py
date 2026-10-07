from uuid import UUID

from pydantic import BaseModel, Field


class ScheduleBindingCreate(BaseModel):
    schedule_id: str = Field(min_length=1, max_length=64)
    project_id: UUID | None = None


class ScheduleBindingRead(BaseModel):
    schedule_id: str
    project_id: UUID | None


class ScheduleSessionEnsure(BaseModel):
    schedule_id: str = Field(min_length=1, max_length=64)
    session_id: UUID
    user_id: UUID
