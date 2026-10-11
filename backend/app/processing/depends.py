from typing import Annotated

from fastapi import Depends

from app.literature_support.processing.pipeline import build_ingestion_service
from app.platform.database import SessionDep, SessionFactoryDep
from app.platform.storage import StorageDep
from app.platform.tasks import TaskSchedulerDep
from app.processing.repo import IngestionRepository
from app.processing.service import IngestionService


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
