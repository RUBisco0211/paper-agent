from fastapi import APIRouter, Response, status

from ..auth.depends import CurrentUser
from ..platform.internal_auth import AgentInternalAuth
from .depends import AgentScheduleGatewayDep, ScheduleBindingServiceDep
from .schemas import (
    AgentScheduleCreate,
    AgentScheduleRead,
    ScheduleBindingCreate,
    ScheduleBindingRead,
    ScheduleNotificationUpdate,
    ScheduleResult,
    ScheduleSessionEnsure,
)

router = APIRouter(tags=["schedules"])


@router.post(
    "/internal/agent-schedules",
    response_model=AgentScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_schedule(
    payload: AgentScheduleCreate,
    _auth: AgentInternalAuth,
    service: ScheduleBindingServiceDep,
    gateway: AgentScheduleGatewayDep,
) -> AgentScheduleRead:
    binding, cron, timezone = service.create_for_agent(
        gateway=gateway,
        **payload.model_dump(),
    )
    return AgentScheduleRead(
        schedule_id=binding.schedule_id,
        project_id=binding.project_id,
        cron_expression=cron,
        name=payload.name.strip(),
        prompt=payload.prompt.strip(),
        timezone=timezone,
        time=payload.time,
        weekdays=payload.weekdays,
        notify_email=binding.notify_email,
    )


@router.post(
    "/schedule-bindings",
    response_model=ScheduleBindingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_binding(
    payload: ScheduleBindingCreate,
    user: CurrentUser,
    service: ScheduleBindingServiceDep,
) -> ScheduleBindingRead:
    record = service.create(
        schedule_id=payload.schedule_id,
        user_id=user.id,
        project_id=payload.project_id,
        notify_email=payload.notify_email,
    )
    return ScheduleBindingRead(
        schedule_id=record.schedule_id,
        project_id=record.project_id,
        notify_email=record.notify_email,
    )


@router.get("/schedule-bindings", response_model=list[ScheduleBindingRead])
def list_schedule_bindings(
    user: CurrentUser,
    service: ScheduleBindingServiceDep,
) -> list[ScheduleBindingRead]:
    return [
        ScheduleBindingRead(
            schedule_id=record.schedule_id,
            project_id=record.project_id,
            notify_email=record.notify_email,
        )
        for record in service.list_for_user(user_id=user.id)
    ]


@router.patch("/schedules/{schedule_id}", response_model=ScheduleBindingRead)
def update_schedule_notification(
    schedule_id: str,
    payload: ScheduleNotificationUpdate,
    user: CurrentUser,
    service: ScheduleBindingServiceDep,
) -> ScheduleBindingRead:
    record = service.update_notification(
        schedule_id=schedule_id,
        user_id=user.id,
        notify_email=payload.notify_email,
    )
    return ScheduleBindingRead(
        schedule_id=record.schedule_id,
        project_id=record.project_id,
        notify_email=record.notify_email,
    )


@router.post("/internal/schedule-results")
def notify_schedule_result(
    payload: ScheduleResult,
    _auth: AgentInternalAuth,
    service: ScheduleBindingServiceDep,
) -> dict:
    enqueued = service.notify_result(**payload.model_dump())
    return {"accepted": True, "notify_email": enqueued}


@router.delete("/schedule-bindings/{schedule_id}", status_code=204)
def delete_schedule_binding(
    schedule_id: str,
    user: CurrentUser,
    service: ScheduleBindingServiceDep,
) -> Response:
    service.delete(schedule_id=schedule_id, user_id=user.id)
    return Response(status_code=204)


@router.post("/internal/schedule-sessions", response_model=ScheduleBindingRead)
def ensure_schedule_session(
    payload: ScheduleSessionEnsure,
    _auth: AgentInternalAuth,
    service: ScheduleBindingServiceDep,
) -> ScheduleBindingRead:
    record = service.ensure_run_scope(
        schedule_id=payload.schedule_id,
        session_id=payload.session_id,
        user_id=payload.user_id,
    )
    return ScheduleBindingRead(
        schedule_id=record.schedule_id,
        project_id=record.project_id,
        notify_email=record.notify_email,
    )
