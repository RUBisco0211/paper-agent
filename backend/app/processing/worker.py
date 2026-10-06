"""Run queued ingestion jobs outside the HTTP process."""

import time

import structlog

from ..embedding import build_embedding_adapter
from ..ingestion.repo import IngestionRepository
from ..platform.config import settings
from ..platform.database import SessionFactory, SessionLocal
from ..platform.logging import configure_logging
from ..platform.storage import get_object_storage
from ..scholar.metadata import build_default_resolver
from .mineru import MineruParser
from .service import IngestionPipeline

logger = structlog.get_logger(__name__)


class IngestionWorker:
    def __init__(
        self, *, session_factory: SessionFactory, pipeline: IngestionPipeline
    ) -> None:
        self._session_factory = session_factory
        self._pipeline = pipeline

    def recover_interrupted(self) -> int:
        with self._session_factory() as session:
            recovered = IngestionRepository(session).recover_interrupted_jobs()
        if recovered:
            logger.warning("worker.jobs_recovered", count=recovered)
        return recovered

    def run_once(self) -> bool:
        with self._session_factory() as session:
            job_id = IngestionRepository(session).claim_next_queued_job()
        if job_id is None:
            return False
        self._pipeline.run_sync(job_id)
        return True


def main() -> None:
    configure_logging()
    pipeline = IngestionPipeline(
        scheduler=None,
        session_factory=SessionLocal,
        storage=get_object_storage(),
        mineru=MineruParser(
            base_url=settings.mineru_api_url,
            api_key=settings.mineru_api_key,
            timeout_seconds=settings.mineru_timeout_seconds,
        ),
        resolver=build_default_resolver(),
        embeddings=build_embedding_adapter(),
    )
    worker = IngestionWorker(session_factory=SessionLocal, pipeline=pipeline)
    worker.recover_interrupted()
    logger.info("worker.started")
    while True:
        if not worker.run_once():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
