from typing import Annotated

from fastapi import Depends

from ..library.persistence import PaperRepository
from ..platform.database import SessionDep
from .application import IngestionService
from .persistence import IngestionRepository


def get_ingestion_repository(session: SessionDep) -> IngestionRepository:
    return IngestionRepository(session)


IngestionRepositoryDep = Annotated[
    IngestionRepository,
    Depends(get_ingestion_repository),
]


def get_ingestion_service(
    repository: IngestionRepositoryDep,
    session: SessionDep,
) -> IngestionService:
    return IngestionService(repository, PaperRepository(session))


IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
