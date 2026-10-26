"""Run queued downloads and queued runs outside the HTTP process."""

import time
from concurrent.futures import ThreadPoolExecutor

import structlog

from app.literature_support.scholar.enrichment import MetadataEnricher
from app.literature_support.scholar.metadata import build_default_resolver
from app.literature_support.scholar.pdf_fetch import PdfFetcher
from app.literature_support.scholar.pdf_sources import DoiPdfLocator
from app.pipelines.download import DownloadService
from app.pipelines.pipeline import LEASE_SECONDS, RunPipeline, build_run_pipeline
from app.pipelines.repo import RunRepository
from app.platform.config import settings
from app.platform.database import SessionFactory, SessionLocal
from app.platform.logging import configure_logging
from app.platform.storage import get_object_storage
from app.platform.tasks import InlineTaskScheduler

logger = structlog.get_logger(__name__)


class PipelineWorker:
    """One loop over both queues: fetch files first, then process papers."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        downloads: DownloadService,
        runs: RunPipeline,
    ) -> None:
        self._session_factory = session_factory
        self._downloads = downloads
        self._runs = runs

    def recover(self) -> None:
        """Return interrupted downloads to the queue and fail dead runs."""
        recovered = self._downloads.recover_interrupted()
        if recovered:
            logger.warning("worker.downloads_recovered", count=recovered)
        with self._session_factory() as session:
            expired = RunRepository(session).reclaim_expired()
        if expired:
            logger.warning("worker.runs_reclaimed", count=expired)

    def run_downloads(self, *, limit: int) -> int:
        done = 0
        for _ in range(limit):
            download_id = self._downloads.claim_next()
            if download_id is None:
                break
            self._downloads.run(download_id)
            done += 1
        return done

    def run_runs(self, *, concurrency: int) -> int:
        with self._session_factory() as session:
            RunRepository(session).reclaim_expired()
        run_ids: list = []
        for _ in range(concurrency):
            with self._session_factory() as session:
                run_id = RunRepository(session).claim_next(
                    lease_seconds=LEASE_SECONDS
                )
            if run_id is None:
                break
            run_ids.append(run_id)
        if not run_ids:
            return 0
        with ThreadPoolExecutor(max_workers=len(run_ids)) as executor:
            futures = [
                executor.submit(self._runs.run_sync, run_id) for run_id in run_ids
            ]
            for future in futures:
                future.result()
        return len(run_ids)


def main() -> None:
    configure_logging()
    storage = get_object_storage()
    resolver = build_default_resolver()
    downloads = DownloadService(
        session_factory=SessionLocal,
        storage=storage,
        fetcher=PdfFetcher(max_bytes=settings.max_pdf_bytes),
        resolver=resolver,
        locator=DoiPdfLocator(),
        # A downloaded paper deserves its bibliographic facts just like an
        # uploaded one; the lookup runs beside the run, never inside it.
        enrichment=MetadataEnricher(
            storage=storage,
            resolver=resolver,
            session_factory=SessionLocal,
        ),
    )
    runs = build_run_pipeline(
        storage=storage,
        session_factory=SessionLocal,
        scheduler=InlineTaskScheduler(),
    )
    worker = PipelineWorker(
        session_factory=SessionLocal, downloads=downloads, runs=runs
    )
    worker.recover()
    logger.info("worker.started")
    while True:
        fetched = worker.run_downloads(limit=settings.import_concurrency)
        processed = worker.run_runs(concurrency=settings.import_concurrency)
        if not fetched and not processed:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
