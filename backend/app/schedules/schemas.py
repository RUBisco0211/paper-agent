from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ScheduleBindingCreate(BaseModel):
    schedule_id: str = Field(min_length=1, max_length=64)
    project_id: UUID | None = None
    notify_email: bool = False


class ScheduleBindingRead(BaseModel):
    schedule_id: str
    project_id: UUID | None
    notify_email: bool = False


class ScheduleNotificationUpdate(BaseModel):
    notify_email: bool


class ScheduleSessionEnsure(BaseModel):
    schedule_id: str = Field(min_length=1, max_length=64)
    session_id: UUID
    user_id: UUID


class ScheduleResult(ScheduleSessionEnsure):
    name: str = Field(min_length=1, max_length=120)
    status: Literal["success", "failed"]
    markdown: str = ""
    error: str | None = None


class AgentScheduleCreate(BaseModel):
    user_id: UUID
    agent_id: str = Field(min_length=1, max_length=64)
    session_id: UUID
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=10000)
    time: str = Field(min_length=5, max_length=5)
    weekdays: list[str] = Field(min_length=1, max_length=7)
    notify_email: bool = False


class AgentScheduleRead(BaseModel):
    notify_email: bool = False
    schedule_id: str
    project_id: UUID | None
    cron_expression: str
    name: str
    prompt: str
    timezone: str
    time: str
    weekdays: list[str]
