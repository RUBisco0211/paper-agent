from typing import Annotated

from fastapi import Depends

from ..platform.database import SessionDep
from ..platform.storage import StorageDep
from .application import PaperLibraryService
from .persistence import PaperRepository
from .ports import IngestionStarter


def get_paper_repository(session: SessionDep) -> PaperRepository:
    return PaperRepository(session)


PaperRepositoryDep = Annotated[PaperRepository, Depends(get_paper_repository)]


def get_ingestion_starter(session: SessionDep) -> IngestionStarter:
    """Build the ingestion service without creating an import cycle.

    The import is intentionally local: the ingestion module depends on library
    persistence, so a module-level import here would close the loop.
    """
    from ..ingestion.application import IngestionService
    from ..ingestion.persistence import IngestionRepository

    return IngestionService(IngestionRepository(session), PaperRepository(session))


IngestionStarterDep = Annotated[IngestionStarter, Depends(get_ingestion_starter)]


def get_paper_library_service(
    papers: PaperRepositoryDep,
    ingestion: IngestionStarterDep,
    storage: StorageDep,
) -> PaperLibraryService:
    return PaperLibraryService(papers, ingestion, storage)


PaperLibraryServiceDep = Annotated[
    PaperLibraryService,
    Depends(get_paper_library_service),
]
