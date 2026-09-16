from typing import Annotated

from fastapi import Depends

from ..library.dependencies import PaperLibraryServiceDep
from ..platform.database import SessionDep
from ..platform.storage import StorageDep
from ..projects.persistence import ProjectRepository
from .application import ProjectSessionPurger, SessionService
from .entries import EntryStore
from .persistence import SessionRepository


def get_entry_store(storage: StorageDep) -> EntryStore:
    return EntryStore(storage)


EntryStoreDep = Annotated[EntryStore, Depends(get_entry_store)]


def get_session_repository(session: SessionDep) -> SessionRepository:
    return SessionRepository(session)


SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]


def get_session_service(
    repository: SessionRepositoryDep,
    entries: EntryStoreDep,
    library: PaperLibraryServiceDep,
    session: SessionDep,
) -> SessionService:
    return SessionService(
        repository,
        entries,
        library,
        ProjectRepository(session),
    )


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


def build_project_session_cleaner(
    *,
    session: SessionDep,
    storage: StorageDep,
) -> ProjectSessionPurger:
    """Cleanup implementation handed to the projects module."""
    return ProjectSessionPurger(SessionRepository(session), EntryStore(storage))
