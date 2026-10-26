"""Turn a queued identifier into a stored file, then join it to its run.

A download never decides whether a paper exists; the file hash does. When two
users ask for the same DOI at once, whichever finishes second finds the paper
that is already there and joins it, so the duplication stops at the object
store rather than in the database.
"""

import tempfile
from pathlib import Path
from uuid import UUID

import structlog

from app.literature_support.scholar.identifiers import (
    Identifier,
    IdentifierType,
    parse_identifier,
)
from app.literature_support.scholar.metadata import MetadataResolver
from app.literature_support.scholar.pdf_fetch import PdfFetcher
from app.literature_support.scholar.pdf_sources import DoiPdfLocator
from app.platform.config import settings
from app.platform.database import SessionFactory
from app.platform.errors import AppError, ErrorCode
from app.platform.storage import ObjectStorage

from ..library.repo import PaperRepository
from ..library.service import PaperLibraryService
from ..pipelines.repo import DownloadRepository
from ..pipelines.runs import RunService

logger = structlog.get_logger(__name__)


class DownloadService:
    """Fetch what one download row asked for and record where it landed."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        storage: ObjectStorage,
        fetcher: PdfFetcher,
        resolver: MetadataResolver,
        locator: DoiPdfLocator,
        enrichment=None,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._fetcher = fetcher
        self._resolver = resolver
        self._locator = locator
        self._enrichment = enrichment

    def claim_next(self) -> UUID | None:
        with self._session_factory() as session:
            return DownloadRepository(session).claim_next()

    def recover_interrupted(self) -> int:
        with self._session_factory() as session:
            return DownloadRepository(session).recover_interrupted()

    def run(self, download_id: UUID) -> None:
        session = self._session_factory()
        try:
            downloads = DownloadRepository(session)
            record = downloads.get(download_id)
            if record is None or record.is_finished:
                return
            identifier = parse_identifier(record.identifier)
            try:
                with tempfile.TemporaryDirectory(
                    prefix="paper-agent-download-"
                ) as directory:
                    fetched = self._fetch(
                        identifier, staging=Path(directory) / "download.pdf"
                    )
                    papers = PaperRepository(session)
                    library = PaperLibraryService(
                        papers,
                        _NoFurtherRuns(),
                        self._enrichment or _NoEnrichment(),
                        self._storage,
                    )
                    with fetched.path.open("rb") as handle:
                        paper = library.adopt_source(
                            stream=handle,
                            filename=f"{identifier.value}.pdf",
                        )
                    # The identifier is a fact about the paper, not the request.
                    _record_identifier(papers, paper.id, identifier)
                    papers.commit()
            except AppError as exc:
                downloads.finish_failure(download_id, error_message=exc.message)
                downloads.commit()
                logger.info(
                    "pipelines.download.failed",
                    download_id=str(download_id),
                    error_code=str(exc.code),
                )
                return

            run = RunService(session_factory=self._session_factory).request(
                user_id=record.user_id, paper_id=paper.id
            )
            downloads.finish_success(
                download_id,
                paper_id=paper.id,
                run_id=run.id,
                source_url=fetched.source_url,
            )
            downloads.commit()
            logger.info(
                "pipelines.download.stored",
                download_id=str(download_id),
                paper_id=str(paper.id),
                run_id=str(run.id),
            )
        finally:
            session.close()

    # Internals -------------------------------------------------------------
    def _fetch(self, identifier: Identifier, *, staging: Path) -> "_Fetched":
        """First candidate that yields a file; raises when none does."""
        attempted: set[str] = set()
        last_error = ErrorCode.PAPER_PDF_NOT_AVAILABLE
        candidates = list(self._candidate_urls(identifier))
        if identifier.type is IdentifierType.DOI:
            candidates.extend(self._locator_urls(identifier.value))
        for candidate in candidates:
            if candidate in attempted:
                continue
            attempted.add(candidate)
            try:
                downloaded = self._fetcher.download(candidate, destination=staging)
                return _Fetched(path=downloaded.path, source_url=candidate)
            except AppError as exc:
                last_error = exc.code
                logger.info(
                    "pipelines.download.source_failed",
                    error_code=str(exc.code),
                )
        raise AppError("没有找到可用的原文", code=last_error, status_code=422)

    def _candidate_urls(self, identifier: Identifier) -> list[str]:
        try:
            outcome = self._resolver.resolve(identifier)
        except AppError:
            outcome = None
        urls: list[str] = []
        metadata = outcome.metadata if outcome is not None else None
        if metadata is not None and metadata.pdf_url:
            urls.append(metadata.pdf_url)
        if identifier.type is IdentifierType.ARXIV:
            urls.append(f"{settings.arxiv_pdf_url.rstrip('/')}/{identifier.value}")
        return urls

    def _locator_urls(self, doi: str) -> list[str]:
        try:
            return self._locator.find(doi)
        except AppError:
            return []


class _Fetched:
    """A downloaded file plus the address it came from."""

    __slots__ = ("path", "source_url")

    def __init__(self, *, path: Path, source_url: str) -> None:
        self.path = path
        self.source_url = source_url


class _NoFurtherRuns:
    """adopt_source never starts a run itself; the caller already has one."""

    def request(self, *, user_id, paper_id):
        raise AssertionError("adopt_source must not request a run")

    def latest_for_papers(self, paper_ids):
        return {}


class _NoEnrichment:
    """Used when no enrichment was wired, so adoption stays silent."""

    def submit(self, paper_id, identifiers=()) -> None:
        return None


def _record_identifier(
    papers: PaperRepository, paper_id: UUID, identifier: Identifier
) -> None:
    paper = papers.get_paper(paper_id)
    if paper is None:
        return
    papers.set_paper_metadata(
        paper_id,
        bibliographic=paper.bibliographic,
        metadata_sources=paper.metadata_sources,
        doi=identifier.value if identifier.type is IdentifierType.DOI else None,
        arxiv_id=(
            identifier.full_value
            if identifier.type is IdentifierType.ARXIV
            else None
        ),
    )
