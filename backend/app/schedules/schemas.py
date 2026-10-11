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


class AgentScheduleCreate(BaseModel):
    user_id: UUID
    agent_id: str = Field(min_length=1, max_length=64)
    session_id: UUID
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=10000)
    time: str = Field(min_length=5, max_length=5)
    weekdays: list[str] = Field(min_length=1, max_length=7)


class AgentScheduleRead(BaseModel):
    schedule_id: str
    project_id: UUID | None
    cron_expression: str
    name: str
    prompt: str
    timezone: str
    time: str
    weekdays: list[str]
