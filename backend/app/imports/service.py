"""Import use case: resolve an identifier, then try to get the full text.

Metadata success already produces a usable library entry; a missing or failed
PDF download only marks the entry as waiting for full text.
"""

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select

from app.literature_support.scholar.identifiers import (
    Identifier,
    IdentifierType,
    parse_identifier,
)
from app.literature_support.scholar.metadata import MetadataResolver
from app.literature_support.scholar.enrichment import MetadataEnricher
from app.literature_support.scholar.pdf_fetch import DownloadedPdf, PdfFetcher

from ..library.repo import PaperRepository
from ..library.service import LibraryEntry, PaperLibraryService
from ..platform.database import SessionFactory
from ..platform.errors import (
    AppError,
    ConflictError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from ..platform.security import create_candidate_token, read_candidate_token
from ..platform.storage import ObjectStorage, paper_pdf_key
from ..platform.tasks import TaskScheduler
from ..projects.repo import ProjectRepository
from ..sessions.repo import SessionBindingRepository
from ..sessions.service import SessionBindingService
from .domain import ImportStatus, PaperImport, source_of
from .ports import (
    ImportRunner,
    ImportStarterFactory,
    PaperDiscoveryAdapter,
    PdfSourceLocator,
)
from .repo import ImportApprovalRecord, ImportRepository

logger = structlog.get_logger(__name__)


class DiscoveryService:
    def __init__(
        self, bindings: SessionBindingService, provider: PaperDiscoveryAdapter
    ) -> None:
        self._bindings = bindings
        self._provider = provider

    def search_manual(self, *, query: str, limit: int) -> dict:
        result = self._provider.search(query, limit)
        return {"papers": result.papers, "failed_sources": result.failed_sources}

    def search(
        self, *, user_id: UUID, session_id: UUID, query: str, limit: int
    ) -> dict:
        self._bindings.require(session_id=session_id, user_id=user_id)
        result = self._provider.search(query, limit)
        candidates = result.papers
        for candidate in candidates:
            identifier = candidate.get("doi")
            source_id = candidate.get("source_id")
            try:
                if not isinstance(identifier, str) or not isinstance(source_id, str):
                    continue
                parse_identifier(identifier)
            except AppError:
                continue
            candidate["candidate_token"] = create_candidate_token(
                user_id=str(user_id),
                session_id=str(session_id),
                source_id=source_id,
                identifier=identifier,
                title=candidate.get("title")
                if isinstance(candidate.get("title"), str)
                else None,
            )
        return {"papers": candidates, "failed_sources": result.failed_sources}


class ImportApprovalService:
    def __init__(
        self, session_factory: SessionFactory, importer: "ImportService"
    ) -> None:
        self._session_factory = session_factory
        self._importer = importer

    def approve(
        self, *, user_id: UUID, session_id: UUID, candidate_tokens: list[str]
    ) -> ImportApprovalRecord:
        if not 1 <= len(candidate_tokens) <= 10:
            raise ValidationError("请选择 1–10 篇文献")
        candidates = []
        seen = set()
        for token in candidate_tokens:
            claims = read_candidate_token(token)
            if claims.get("uid") != str(user_id) or claims.get("sid") != str(
                session_id
            ):
                raise ForbiddenError("候选文献不属于当前会话")
            identifier = parse_identifier(claims.get("identifier", ""))
            source_id = claims.get("source_id")
            if not isinstance(source_id, str) or not source_id.startswith("https://"):
                raise ValidationError("候选文献信息无效")
            if identifier.value in seen:
                continue
            seen.add(identifier.value)
            candidates.append(
                {
                    "identifier": identifier.value,
                    "source_id": source_id,
                    "title": claims.get("title")
                    if isinstance(claims.get("title"), str)
                    else None,
                }
            )
        with self._session_factory() as session:
            SessionBindingService(
                SessionBindingRepository(session), ProjectRepository(session)
            ).require(session_id=session_id, user_id=user_id)
            record = ImportApprovalRecord(
                user_id=user_id,
                session_id=session_id,
                candidates=candidates,
                status="pending",
                expires_at=datetime.now(UTC) + timedelta(minutes=15),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def consume(self, *, user_id: UUID, session_id: UUID) -> list[dict]:
        with self._session_factory() as session:
            binding = SessionBindingService(
                SessionBindingRepository(session), ProjectRepository(session)
            ).require(session_id=session_id, user_id=user_id)
            record = session.scalar(
                select(ImportApprovalRecord)
                .where(
                    ImportApprovalRecord.user_id == user_id,
                    ImportApprovalRecord.session_id == session_id,
                )
                .order_by(
                    ImportApprovalRecord.created_at.desc(),
                    ImportApprovalRecord.id.desc(),
                )
                .limit(1)
                .with_for_update()
            )
            if record is None or record.expires_at < datetime.now(UTC):
                raise ForbiddenError("请先在检索结果中确认要入库的文献")
            if record.status == "started":
                return record.results or []
            results = []
            for candidate in record.candidates:
                try:
                    item = self._importer.start(
                        user_id=user_id,
                        identifier_text=candidate["identifier"],
                    )
                    results.append(
                        {
                            "identifier": candidate["identifier"],
                            "import_id": str(item.id),
                            "status": str(item.status),
                        }
                    )
                except AppError as exc:
                    results.append(
                        {
                            "identifier": candidate["identifier"],
                            "error_code": str(exc.code),
                            "status": "failed",
                        }
                    )
            record.results = results
            record.status = "started"
            session.commit()
            return results

    def preview(self, *, user_id: UUID, session_id: UUID) -> list[dict]:
        with self._session_factory() as session:
            SessionBindingService(
                SessionBindingRepository(session), ProjectRepository(session)
            ).require(session_id=session_id, user_id=user_id)
            record = session.scalar(
                select(ImportApprovalRecord)
                .where(
                    ImportApprovalRecord.user_id == user_id,
                    ImportApprovalRecord.session_id == session_id,
                )
                .order_by(
                    ImportApprovalRecord.created_at.desc(),
                    ImportApprovalRecord.id.desc(),
                )
                .limit(1)
            )
            if (
                record is None
                or record.status != "pending"
                or record.expires_at < datetime.now(UTC)
            ):
                raise ForbiddenError("本次选文授权已失效，请重新选择")
            return [
                {
                    "title": item.get("title"),
                    "identifier": item["identifier"],
                    "source_id": item["source_id"],
                }
                for item in record.candidates
            ]


class ImportService:
    """Start identifier imports and report the queue the user sees."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        storage: ObjectStorage,
        resolver: MetadataResolver,
        pdf_fetcher: PdfFetcher,
        pdf_locator: PdfSourceLocator,
        scheduler: TaskScheduler,
        import_starter_factory: ImportStarterFactory,
        runner: ImportRunner | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._resolver = resolver
        self._pdf_fetcher = pdf_fetcher
        self._pdf_locator = pdf_locator
        self._scheduler = scheduler
        self._import_starter_factory = import_starter_factory
        self._runner = runner

    # API surface -----------------------------------------------------------
    def start(
        self,
        *,
        user_id: UUID,
        identifier_text: str,
    ) -> PaperImport:
        """Queue an identifier import; the paper appears once it is usable."""
        identifier = parse_identifier(identifier_text)
        session = self._session_factory()
        try:
            repository = ImportRepository(session)
            existing = repository.find_by_identifier(
                identifier_type=identifier.type.value,
                identifier=identifier.value,
            )
            if existing is None:
                import_id = repository.add(
                    initiated_by=user_id,
                    identifier_type=identifier.type.value,
                    identifier=identifier.value,
                ).id
            else:
                import_id = existing.id
                if existing.status is not ImportStatus.READY:
                    repository.reset_for_retry(import_id)
            repository.commit()
        finally:
            session.close()

        self._scheduler.submit(
            lambda: self._run(import_id),
            name=f"import:{import_id}",
        )
        logger.info(
            "service.import.queued",
            import_id=str(import_id),
            identifier_type=identifier.type.value,
        )
        return self.get(user_id=user_id, import_id=import_id)

    def entry_id_for(self, *, record: PaperImport, user_id: UUID) -> UUID | None:
        """The user's own entry for this import's paper, once it exists."""
        if record.paper_id is None:
            return None
        session = self._session_factory()
        try:
            entry = PaperRepository(session).get_user_paper_for_paper(
                user_id=user_id,
                paper_id=record.paper_id,
            )
            return entry.id if entry is not None else None
        finally:
            session.close()

    def retry_import(self, import_id: UUID) -> PaperImport:
        """Run the unfinished stages again, skipping completed artifacts."""
        session = self._session_factory()
        try:
            importer = self._import_starter_factory(
                session=session,
                storage=self._storage,
                session_factory=self._session_factory,
                scheduler=self._scheduler,
            )
            return importer.retry(import_id)
        finally:
            session.close()

    def get(self, *, user_id: UUID, import_id: UUID) -> PaperImport:
        session = self._session_factory()
        try:
            record = ImportRepository(session).get(import_id)
        finally:
            session.close()
        # The record is shared by everyone who wanted this paper, but only the
        # person who started it may read its progress; anyone else gets the
        # same answer as for an unknown record.
        if record is None or record.initiated_by != user_id:
            raise NotFoundError("入库记录不存在", code=ErrorCode.IMPORT_NOT_FOUND)
        return record

    def queue(self, *, user_id: UUID, limit: int = 100) -> list[dict]:
        """Imports this user started, newest first, with their stage progress."""
        with self._session_factory() as session:
            imports = ImportRepository(session).list_for_user(
                user_id=user_id, limit=limit
            )
            papers = PaperRepository(session)
            items: list[dict] = []
            for item in imports:
                paper = (
                    papers.get_paper(item.paper_id)
                    if item.paper_id is not None
                    else None
                )
                items.append(
                    {
                        "id": str(item.id),
                        "identifier": item.identifier,
                        "identifier_type": item.identifier_type,
                        "title": paper.title if paper else None,
                        "paper_id": str(item.paper_id) if item.paper_id else None,
                        "status": item.status.value,
                        "stage": (
                            item.current_stage.value if item.current_stage else None
                        ),
                        "created_at": item.created_at.isoformat(),
                        "error_code": item.error_code,
                        "stages": [
                            {
                                "stage": stage.stage.value,
                                "status": stage.status.value,
                                "attempt": stage.attempt,
                                "error_code": stage.error_code,
                                "error_message": stage.error_message,
                                "progress": stage.progress,
                                "started_at": (
                                    stage.started_at.isoformat()
                                    if stage.started_at
                                    else None
                                ),
                                "finished_at": (
                                    stage.finished_at.isoformat()
                                    if stage.finished_at
                                    else None
                                ),
                            }
                            for stage in item.stages
                        ],
                    }
                )
            return items[:limit]

    # Work ------------------------------------------------------------------
    # Work ------------------------------------------------------------------
    async def _run(self, import_id: UUID) -> None:
        await asyncio.to_thread(self._run_sync, import_id)

    def _run_sync(self, import_id: UUID) -> None:
        """Acquire the source file, then hand the rest to the stage pipeline."""
        session = self._session_factory()
        repository: ImportRepository | None = None
        try:
            repository = ImportRepository(session)
            record = repository.get(import_id)
            if record is None or record.status is not ImportStatus.QUEUED:
                return
            try:
                identifier = parse_identifier(record.identifier)
            except AppError as exc:
                repository.finish(
                    import_id,
                    status=ImportStatus.FAILED,
                    error_code=str(exc.code),
                )
                repository.commit()
                return

            # The source file decides whether this paper can exist at all: an
            # entry always points at a stored file, so a paper row is only
            # created once a download succeeds.
            papers = PaperRepository(session)
            library = self._build_library_service(session, papers)
            attempted: set[str] = set()
            last_error = ErrorCode.PAPER_PDF_NOT_AVAILABLE
            source_error: str | None = None

            paper_id = self._reuse_stored_paper(papers, identifier)
            if paper_id is not None:
                repository.expire_all()
                repository.bind_paper(import_id, paper_id)
                self._open_entry(papers, record.initiated_by, paper_id, identifier)
                repository.commit()
                logger.info(
                    "service.import.reused_stored_file",
                    import_id=str(import_id),
                    paper_id=str(paper_id),
                )
                self._resume_stages(import_id)
                return

            with tempfile.TemporaryDirectory(
                prefix="paper-agent-import-"
            ) as directory:
                staging = Path(directory) / "download.pdf"
                stored = self._download_first(
                    urls=self._candidate_urls(identifier),
                    attempted=attempted,
                    destination=staging,
                )
                if stored is None and identifier.type is IdentifierType.DOI:
                    try:
                        fallback = self._pdf_locator.find(identifier.value)
                    except AppError as exc:
                        fallback = []
                        if not attempted:
                            last_error = exc.code
                    stored = self._download_first(
                        urls=fallback,
                        attempted=attempted,
                        destination=staging,
                    )

                if stored is None:
                    source_error = str(last_error)
                else:
                    with stored.path.open("rb") as handle:
                        paper = library.adopt_source(
                            stream=handle,
                            filename=f"{identifier.value}.pdf",
                        )
                        paper_id = paper.id
                        # The identifier is part of the paper's identity, not
                        # just the request that fetched it.
                        papers.set_paper_metadata(
                            paper.id,
                            bibliographic=paper.bibliographic,
                            metadata_sources=paper.metadata_sources,
                            doi=(
                                identifier.value
                                if identifier.type is IdentifierType.DOI
                                else None
                            ),
                            arxiv_id=(
                                identifier.full_value
                                if identifier.type is IdentifierType.ARXIV
                                else None
                            ),
                        )
                        papers.commit()

            if source_error is not None:
                repository.expire_all()
                repository.finish(
                    import_id,
                    status=ImportStatus.SOURCE_UNAVAILABLE,
                    error_code=source_error,
                )
                repository.commit()
                logger.info(
                    "service.import.source_unavailable",
                    import_id=str(import_id),
                    error_code=source_error,
                )
                return

            repository.expire_all()
            repository.bind_paper(import_id, paper_id)
            self._open_entry(papers, record.initiated_by, paper_id, identifier)
            repository.commit()
            logger.info(
                "service.import.bound",
                import_id=str(import_id),
                paper_id=str(paper_id),
            )

            self._resume_stages(import_id)
        except Exception as exc:
            logger.exception(
                "service.import.crashed",
                import_id=str(import_id),
                error_type=type(exc).__name__,
            )
            if repository is None:
                raise
            try:
                repository.finish(
                    import_id,
                    status=ImportStatus.FAILED,
                    error_code=str(ErrorCode.INTERNAL_ERROR),
                )
                repository.commit()
            except Exception:  # pragma: no cover - last resort
                repository.rollback()
        finally:
            session.close()

    # Internals -------------------------------------------------------------
    def _download_first(
        self,
        *,
        urls: list[str],
        attempted: set[str],
        destination: Path,
    ) -> DownloadedPdf | None:
        """Return the first source file that downloads, or nothing."""
        for url in urls:
            if url in attempted:
                continue
            attempted.add(url)
            try:
                return self._pdf_fetcher.download(url, destination=destination)
            except AppError as exc:
                logger.info(
                    "service.import.pdf_source_failed",
                    error_code=str(exc.code),
                )
        return None

    def _open_entry(
        self,
        papers: PaperRepository,
        user_id: UUID,
        paper_id: UUID,
        identifier: Identifier,
    ) -> None:
        """The entry exists from now on, but stays out of the library for now."""
        papers.link_paper(
            user_id=user_id,
            paper_id=paper_id,
            source=source_of(identifier.type.value),
        )
        papers.commit()

    def _reuse_stored_paper(
        self,
        papers: PaperRepository,
        identifier: Identifier,
    ) -> UUID | None:
        """An arXiv id with a version names exactly one file, already stored."""
        if identifier.type is not IdentifierType.ARXIV or not identifier.version:
            return None
        paper = papers.get_paper_by_arxiv_id(identifier.full_value)
        if paper is None:
            return None
        if not self._storage.exists(paper_pdf_key(paper.file_hash)):
            return None
        return paper.id

    def _resume_stages(self, import_id: UUID) -> None:
        """Run the remaining stages; the import is ready only when they finish."""
        if self._runner is not None:
            self._runner.submit_stages(import_id)
            return
        session = self._session_factory()
        try:
            repository = ImportRepository(session)
            repository.finish(import_id, status=ImportStatus.READY)
            repository.commit()
        finally:
            session.close()

    def _candidate_urls(self, identifier: Identifier) -> list[str]:
        """Where a source file might live for this identifier, best first."""
        outcome = self._resolver.resolve(identifier)
        urls = (
            [outcome.metadata.pdf_url]
            if outcome.metadata is not None and outcome.metadata.pdf_url
            else []
        )
        if identifier.type is IdentifierType.ARXIV:
            # arXiv always serves the PDF under a stable path, so it is the
            # fallback when the provider announces nothing usable.
            urls.append(_arxiv_pdf_url(identifier.value))
        return urls

    def _build_library_service(self, session, papers: PaperRepository):
        importer = self._import_starter_factory(
            session=session,
            storage=self._storage,
            session_factory=self._session_factory,
            scheduler=self._scheduler,
        )
        enrichment = MetadataEnricher(
            storage=self._storage,
            resolver=self._resolver,
            session_factory=self._session_factory,
        )
        return PaperLibraryService(
            papers,
            importer,
            enrichment,
            self._storage,
        )


def _arxiv_pdf_url(arxiv_id: str) -> str:
    from app.platform.config import settings

    return f"{settings.arxiv_pdf_url.rstrip('/')}/{arxiv_id}"
