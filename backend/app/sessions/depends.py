from typing import Annotated

from fastapi import Depends, Request

from ..agent.service import SessionExecutor
from ..conversation.events import EventBroker
from ..conversation.service import EntryStore
from ..library.depends import PaperLibraryServiceDep
from ..platform.config import settings
from ..platform.database import SessionDep
from ..platform.storage import StorageDep
from ..projects.repo import ProjectRepository
from .repo import SessionRepository
from .service import CitationService, ProjectSessionPurger, SessionService


def get_entry_store(storage: StorageDep) -> EntryStore:
    return EntryStore(storage)


EntryStoreDep = Annotated[EntryStore, Depends(get_entry_store)]


def get_session_repository(session: SessionDep) -> SessionRepository:
    return SessionRepository(session)


SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]


def get_event_broker(request: Request) -> EventBroker:
    return request.app.state.event_broker


EventBrokerDep = Annotated[EventBroker, Depends(get_event_broker)]


def get_session_executor(request: Request) -> SessionExecutor:
    """Process-wide executor; it owns the in-flight generations."""
    return request.app.state.session_executor


SessionExecutorDep = Annotated[SessionExecutor, Depends(get_session_executor)]


def get_sse_idle_timeout() -> float:
    return settings.sse_idle_timeout_seconds


SseIdleTimeoutDep = Annotated[float, Depends(get_sse_idle_timeout)]


def get_session_service(
    repository: SessionRepositoryDep,
    entries: EntryStoreDep,
    library: PaperLibraryServiceDep,
    session: SessionDep,
    executor: SessionExecutorDep,
    events: EventBrokerDep,
) -> SessionService:
    return SessionService(
        repository,
        entries,
        library,
        ProjectRepository(session),
        executor,
        events,
    )


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


def build_project_session_cleaner(
    *,
    session: SessionDep,
    storage: StorageDep,
) -> ProjectSessionPurger:
    """Cleanup implementation handed to the projects module."""
    return ProjectSessionPurger(SessionRepository(session), EntryStore(storage))


def get_citation_service(repository: SessionRepositoryDep) -> CitationService:
    return CitationService(repository)


CitationServiceDep = Annotated[CitationService, Depends(get_citation_service)]
