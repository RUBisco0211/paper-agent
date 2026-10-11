"""Narrow internal HTTP operations for agent-created schedules."""

import secrets
from datetime import UTC, datetime
from typing import Annotated

from agentscope.app._manager import SchedulerManager
from agentscope.app.deps import get_scheduler_manager, get_storage
from agentscope.app.storage import (
    ScheduleData,
    ScheduleRecord,
    ScheduleSource,
    SessionSource,
    StorageBase,
)
from agentscope.permission import PermissionMode
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.platform.config import settings

router = APIRouter(prefix="/internal/tool-schedules", tags=["internal"])


def require_internal_key(
    x_agent_internal_key: Annotated[str | None, Header()] = None,
) -> None:
    if (
        not settings.agent_internal_key
        or not x_agent_internal_key
        or not secrets.compare_digest(settings.agent_internal_key, x_agent_internal_key)
    ):
        raise HTTPException(status_code=401, detail="internal_auth_failed")


InternalAuth = Annotated[None, Depends(require_internal_key)]
StorageDep = Annotated[StorageBase, Depends(get_storage)]
SchedulerDep = Annotated[SchedulerManager, Depends(get_scheduler_manager)]


class ToolScheduleCreate(BaseModel):
    user_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=10000)
    cron_expression: str
    timezone: str


class ToolScheduleCreated(BaseModel):
    schedule_id: str


class ScheduleOwner(BaseModel):
    user_id: str


@router.post("", response_model=ToolScheduleCreated, status_code=201)
async def create_tool_schedule(
    body: ToolScheduleCreate,
    storage: StorageDep,
    _auth: InternalAuth = None,
) -> ToolScheduleCreated:
    session = await storage.get_session(body.user_id, body.agent_id, body.session_id)
    if (
        session is None
        or session.user_id != body.user_id
        or session.agent_id != body.agent_id
    ):
        raise HTTPException(status_code=404, detail="session_not_found")
    if session.source == SessionSource.SCHEDULE:
        raise HTTPException(status_code=409, detail="unattended_run")
    model = session.config.chat_model_config
    if model is None:
        raise HTTPException(status_code=409, detail="llm_not_configured")
    record = ScheduleRecord(
        user_id=body.user_id,
        agent_id=body.agent_id,
        data=ScheduleData(
            name=body.name,
            description=body.prompt,
            cron_expression=body.cron_expression,
            timezone=body.timezone,
            enabled=False,
            stateful=False,
            permission_mode=PermissionMode.DONT_ASK,
            chat_model_config=model,
            source=ScheduleSource.AGENT,
            source_session_id=body.session_id,
            started_at=datetime.now(UTC),
        ),
    )
    await storage.upsert_schedule(body.user_id, record)
    return ToolScheduleCreated(schedule_id=record.id)


@router.post("/{schedule_id}/enable", status_code=204)
async def enable_tool_schedule(
    schedule_id: str,
    body: ScheduleOwner,
    _auth: InternalAuth,
    storage: StorageDep,
    scheduler: SchedulerDep,
) -> None:
    record = await storage.get_schedule(body.user_id, schedule_id)
    if record is None or record.data.source != ScheduleSource.AGENT:
        raise HTTPException(status_code=404, detail="schedule_not_found")
    enabled = record.model_copy(
        update={"data": record.data.model_copy(update={"enabled": True})}
    )
    await storage.upsert_schedule(body.user_id, enabled)
    await scheduler.register_schedule(enabled)


@router.delete("/{schedule_id}", status_code=204)
async def delete_tool_schedule(
    schedule_id: str,
    body: ScheduleOwner,
    _auth: InternalAuth,
    storage: StorageDep,
    scheduler: SchedulerDep,
) -> None:
    record = await storage.get_schedule(body.user_id, schedule_id)
    if record is None or record.data.source != ScheduleSource.AGENT:
        raise HTTPException(status_code=404, detail="schedule_not_found")
    await scheduler.remove_schedule(schedule_id)
    await storage.delete_schedule(body.user_id, schedule_id)
