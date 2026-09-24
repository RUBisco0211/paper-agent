from typing import Annotated

from fastapi import Depends

from ..platform.database import SessionDep, SessionFactoryDep
from ..platform.storage import StorageDep
from ..platform.tasks import TaskSchedulerDep
from ..processing.service import build_ingestion_service
from .repo import IngestionRepository
from .service import IngestionService


def get_ingestion_repository(session: SessionDep) -> IngestionRepository:
    return IngestionRepository(session)


IngestionRepositoryDep = Annotated[
    IngestionRepository,
    Depends(get_ingestion_repository),
]


def get_ingestion_service(
    session: SessionDep,
    storage: StorageDep,
    session_factory: SessionFactoryDep,
    scheduler: TaskSchedulerDep,
) -> IngestionService:
    return build_ingestion_service(
        session=session,
        storage=storage,
        session_factory=session_factory,
        scheduler=scheduler,
    )


IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
