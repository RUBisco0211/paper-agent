"""Run queued imports outside the HTTP process."""

import time
from concurrent.futures import ThreadPoolExecutor

import structlog

from app.imports.repo import ImportRepository
from app.literature_support.embedding import build_embedding_adapter
from app.literature_support.importing.mineru import MineruParser
from app.literature_support.importing.pipeline import ImportPipeline
from app.platform.config import settings
from app.platform.database import SessionFactory, SessionLocal
from app.platform.logging import configure_logging
from app.platform.storage import get_object_storage

logger = structlog.get_logger(__name__)


class ImportWorker:
    def __init__(
        self, *, session_factory: SessionFactory, pipeline: ImportPipeline
    ) -> None:
        self._session_factory = session_factory
        self._pipeline = pipeline

    def recover_interrupted(self) -> int:
        with self._session_factory() as session:
            recovered = ImportRepository(session).recover_interrupted()
        if recovered:
            logger.warning("worker.imports_recovered", count=recovered)
        return recovered

    def run_once(self) -> bool:
        with self._session_factory() as session:
            import_id = ImportRepository(session).claim_next_queued()
        if import_id is None:
            return False
        self._pipeline.run_sync(import_id)
        return True

    def run_batch(self, *, max_concurrent_imports: int) -> int:
        if max_concurrent_imports < 1:
            raise ValueError("max_concurrent_imports must be positive")
        import_ids = []
        for _ in range(max_concurrent_imports):
            with self._session_factory() as session:
                import_id = ImportRepository(session).claim_next_queued()
            if import_id is None:
                break
            import_ids.append(import_id)
        if not import_ids:
            return 0
        with ThreadPoolExecutor(max_workers=max_concurrent_imports) as executor:
            futures = [
                executor.submit(self._pipeline.run_sync, import_id)
                for import_id in import_ids
            ]
            for future in futures:
                future.result()
        return len(import_ids)


def main() -> None:
    configure_logging()
    pipeline = ImportPipeline(
        scheduler=None,
        session_factory=SessionLocal,
        storage=get_object_storage(),
        mineru=MineruParser(
            base_url=settings.mineru_api_url,
            api_key=settings.mineru_api_key,
            timeout_seconds=settings.mineru_timeout_seconds,
        ),
        embeddings=build_embedding_adapter(),
    )
    worker = ImportWorker(session_factory=SessionLocal, pipeline=pipeline)
    worker.recover_interrupted()
    logger.info("worker.started")
    while True:
        if not worker.run_batch(max_concurrent_imports=settings.import_concurrency):
            time.sleep(0.5)


if __name__ == "__main__":
    main()
