from typing import Annotated

from fastapi import Depends

from ..library.persistence import PaperRepository
from ..platform.config import settings
from ..platform.database import SessionDep, SessionFactory, SessionFactoryDep
from ..platform.storage import StorageDep
from ..platform.tasks import TaskScheduler, TaskSchedulerDep
from ..retrieval.embedding import build_embedding_adapter
from ..scholar.metadata import build_default_resolver
from .application import IngestionService
from .mineru import MineruParser
from .persistence import IngestionRepository
from .pipeline import IngestionPipeline


def build_ingestion_service(
    *,
    session: SessionDep,
    storage: StorageDep,
    session_factory: SessionFactory,
    scheduler: TaskScheduler,
) -> IngestionService:
    """Assemble the ingestion use case together with its stage runner.

    Exposed as a plain function so the library module can reuse the exact same
    wiring without importing this module at import time.
    """
    papers = PaperRepository(session)
    pipeline = IngestionPipeline(
        scheduler=scheduler,
        session_factory=session_factory,
        storage=storage,
        mineru=MineruParser(
            base_url=settings.mineru_api_url,
            api_key=settings.mineru_api_key,
            timeout_seconds=settings.mineru_timeout_seconds,
        ),
        resolver=build_default_resolver(),
        embeddings=build_embedding_adapter(),
        target_tokens=settings.chunk_token_num,
        max_chars=settings.chunk_max_chars,
    )
    return IngestionService(IngestionRepository(session), papers, runner=pipeline)


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
