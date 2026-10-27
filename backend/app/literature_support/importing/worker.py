"""Run queued downloads and queued runs outside the HTTP process."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import structlog

from app.literature_support.scholar.enrichment import MetadataEnricher
from app.literature_support.scholar.metadata import build_default_resolver
from app.literature_support.scholar.pdf_fetch import PdfFetcher
from app.literature_support.scholar.pdf_sources import DoiPdfLocator
from app.pipelines.domain import RunStage
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

    def run_stage(self, stage: RunStage, *, concurrency: int) -> int:
        """Run up to `concurrency` runs of one stage, then give the threads back.

        Each stage is claimed on its own, so a slow parse never holds a slot
        that embedding could be using.
        """
        run_ids: list[UUID] = []
        for _ in range(concurrency):
            with self._session_factory() as session:
                run_id = RunRepository(session).claim_next(
                    stage=stage, lease_seconds=LEASE_SECONDS
                )
            if run_id is None:
                break
            run_ids.append(run_id)
        if not run_ids:
            return 0
        with ThreadPoolExecutor(max_workers=len(run_ids)) as executor:
            futures = [
                executor.submit(self._runs.run_sync, run_id, stage=stage)
                for run_id in run_ids
            ]
            for future in futures:
                future.result()
        return len(run_ids)

    def run_all_stages(self) -> int:
        """Drain every stage once, in dependency order."""
        with self._session_factory() as session:
            RunRepository(session).reclaim_expired()
        total = 0
        for stage, concurrency in (
            (RunStage.PARSE, settings.parse_concurrency),
            (RunStage.CHUNK, _chunk_concurrency()),
            (RunStage.EMBED, settings.embed_concurrency),
        ):
            total += self.run_stage(stage, concurrency=concurrency)
        return total


def _chunk_concurrency() -> int:
    """Chunking is local CPU work, so its ceiling is the machine's cores."""
    configured = settings.chunk_concurrency
    if configured > 0:
        return configured
    return max(1, (os.cpu_count() or 2))


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
        fetched = worker.run_downloads(limit=settings.download_concurrency)
        processed = worker.run_all_stages()
        if not fetched and not processed:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
