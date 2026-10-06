from typing import Annotated

from fastapi import Depends

from ..library.depends import PaperLibraryServiceDep
from ..platform.database import SessionDep
from ..schedules.repo import ScheduleBindingRepository
from .ports import ProjectSessionGuard
from .repo import ProjectRepository
from .service import ProjectService


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


def get_project_session_guard(session: SessionDep) -> ProjectSessionGuard:
    from ..sessions.repo import SessionBindingRepository

    return SessionBindingRepository(session)


ProjectSessionGuardDep = Annotated[
    ProjectSessionGuard,
    Depends(get_project_session_guard),
]


def get_project_service(
    repository: ProjectRepositoryDep,
    library: PaperLibraryServiceDep,
    session_guard: ProjectSessionGuardDep,
    session: SessionDep,
) -> ProjectService:
    return ProjectService(
        repository, library, session_guard, ScheduleBindingRepository(session)
    )


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
