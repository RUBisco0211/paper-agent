from typing import Annotated

from fastapi import Depends

from ..platform.database import SessionDep
from ..projects.repo import ProjectRepository
from ..sessions.repo import SessionBindingRepository
from .repo import ScheduleBindingRepository
from .service import ScheduleBindingService


def get_schedule_binding_service(session: SessionDep) -> ScheduleBindingService:
    return ScheduleBindingService(
        ScheduleBindingRepository(session),
        SessionBindingRepository(session),
        ProjectRepository(session),
    )


ScheduleBindingServiceDep = Annotated[
    ScheduleBindingService, Depends(get_schedule_binding_service)
]
