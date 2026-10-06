from fastapi import APIRouter, Response, status

from ..auth.depends import CurrentUser
from ..retrieval.depends import AgentInternalAuth
from .depends import ScheduleBindingServiceDep
from .schemas import ScheduleBindingCreate, ScheduleBindingRead, ScheduleSessionEnsure

router = APIRouter(tags=["schedules"])


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
    )
    return ScheduleBindingRead(
        schedule_id=record.schedule_id, project_id=record.project_id
    )


@router.get("/schedule-bindings", response_model=list[ScheduleBindingRead])
def list_schedule_bindings(
    user: CurrentUser,
    service: ScheduleBindingServiceDep,
) -> list[ScheduleBindingRead]:
    return [
        ScheduleBindingRead(
            schedule_id=record.schedule_id, project_id=record.project_id
        )
        for record in service.list_for_user(user_id=user.id)
    ]


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
        schedule_id=record.schedule_id, project_id=record.project_id
    )
