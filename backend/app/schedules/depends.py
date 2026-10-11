from typing import Annotated

from fastapi import Depends

from ..auth.repo import AuthRepository
from ..platform.agent_schedules import HttpAgentScheduleGateway
from ..platform.database import SessionDep
from ..projects.repo import ProjectRepository
from ..sessions.repo import SessionBindingRepository
from .ports import AgentScheduleGateway
from .repo import ScheduleBindingRepository
from .service import ScheduleBindingService


def get_agent_schedule_gateway() -> AgentScheduleGateway:
    return HttpAgentScheduleGateway()


AgentScheduleGatewayDep = Annotated[
    AgentScheduleGateway, Depends(get_agent_schedule_gateway)
]


def get_schedule_binding_service(session: SessionDep) -> ScheduleBindingService:
    return ScheduleBindingService(
        ScheduleBindingRepository(session),
        SessionBindingRepository(session),
        ProjectRepository(session),
        AuthRepository(session),
    )


ScheduleBindingServiceDep = Annotated[
    ScheduleBindingService, Depends(get_schedule_binding_service)
]
