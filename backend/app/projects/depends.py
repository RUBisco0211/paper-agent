from typing import Annotated

from fastapi import Depends

from ..library.depends import PaperLibraryServiceDep
from ..platform.database import SessionDep
from ..platform.storage import StorageDep
from .ports import ProjectSessionCleaner
from .repo import ProjectRepository
from .service import ProjectService


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


def get_project_session_cleaner(
    session: SessionDep,
    storage: StorageDep,
) -> ProjectSessionCleaner:
    """Purge the sessions bound to a project before the project row goes away.

    The import is local because the sessions module depends on projects.
    """
    from ..sessions.depends import build_project_session_cleaner

    return build_project_session_cleaner(session=session, storage=storage)


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
