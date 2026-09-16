from typing import Annotated

from fastapi import Depends

from ..library.dependencies import PaperLibraryServiceDep
from ..platform.database import SessionDep
from .application import ProjectService
from .persistence import ProjectRepository
from .ports import NoopProjectSessionCleaner, ProjectSessionCleaner


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


def get_project_session_cleaner() -> ProjectSessionCleaner:
    """Session cleanup boundary for project deletion.

    The sessions module replaces this dependency once it owns session storage;
    until then deleting a project only removes the project itself.
    """
    return NoopProjectSessionCleaner()


ProjectSessionCleanerDep = Annotated[
    ProjectSessionCleaner,
    Depends(get_project_session_cleaner),
]


def get_project_service(
    repository: ProjectRepositoryDep,
    library: PaperLibraryServiceDep,
    session_cleaner: ProjectSessionCleanerDep,
) -> ProjectService:
    return ProjectService(repository, library, session_cleaner)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
