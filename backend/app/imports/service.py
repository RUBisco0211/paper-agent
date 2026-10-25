"""Import use case: resolve an identifier, then try to get the full text.

Metadata success already produces a usable library entry; a missing or failed
PDF download only marks the entry as waiting for full text.
"""

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
from .domain import ACTIVE_STATUSES, ImportStatus, PaperImport, source_of
from .ports import (
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
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._resolver = resolver
        self._pdf_fetcher = pdf_fetcher
        self._pdf_locator = pdf_locator
        self._scheduler = scheduler
        self._import_starter_factory = import_starter_factory

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
            current_status = "new"
            current_paper_id = None
            if existing is None:
                import_id = repository.add(
                    initiated_by=user_id,
                    identifier_type=identifier.type.value,
                    identifier=identifier.value,
                ).id
            else:
                import_id = existing.id
                # Re-read inside this session: the row may have advanced since
                # the lookup, and every branch below depends on its status.
                current = repository.get(import_id) or existing
                current_status = current.status.value
                current_paper_id = current.paper_id
                if current.status is ImportStatus.READY:
                    # Already usable: this user only needs their own entry.
                    self._join_ready_paper(
                        session, record=current, user_id=user_id
                    )
                elif current.status in ACTIVE_STATUSES:
                    # Someone else is still working on it; join without
                    # restarting their progress.
                    self._join_running_import(
                        session, record=current, user_id=user_id
                    )
                else:
                    repository.reset_for_retry(import_id)
            repository.commit()
            logger.info(
                "service.import.start_state",
                import_id=str(import_id),
                status=current_status,
                paper_id=str(current_paper_id) if current_paper_id else None,
            )
        finally:
            session.close()

        # The worker owns execution: it claims queued imports and runs every
        # stage, including the download this request only recorded.
        logger.info(
            "service.import.queued",
            import_id=str(import_id),
            identifier_type=identifier.type.value,
        )
        return self.get(user_id=user_id, import_id=import_id)

    def _join_ready_paper(
        self,
        session,
        *,
        record: PaperImport,
        user_id: UUID,
    ) -> None:
        """Give a user an entry for a paper whose import already finished."""
        logger.info(
            "service.import.join_ready",
            import_id=str(record.id),
            paper_id=str(record.paper_id) if record.paper_id else None,
            user_id=str(user_id),
        )
        if record.paper_id is None:
            return
        papers = PaperRepository(session)
        existing = papers.get_user_paper_for_paper(
            user_id=user_id, paper_id=record.paper_id
        )
        if existing is not None:
            return
        papers.add_user_paper(
            user_id=user_id,
            paper_id=record.paper_id,
            source=source_of(record.identifier_type),
            ready=True,
        )

    def _join_running_import(
        self,
        session,
        *,
        record: PaperImport,
        user_id: UUID,
    ) -> None:
        """Join an import still running; the entry is revealed when it ends."""
        if record.paper_id is None:
            # The source stage has not bound a paper yet, so there is nothing
            # to link; this user's entry appears when the import is revealed.
            return
        papers = PaperRepository(session)
        papers.link_paper(
            user_id=user_id,
            paper_id=record.paper_id,
            source=source_of(record.identifier_type),
        )

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
        if record is None:
            raise NotFoundError("入库记录不存在", code=ErrorCode.IMPORT_NOT_FOUND)
        # The record is shared, so anyone who started it or who holds an entry
        # for its paper may read its progress. Everyone else gets the same
        # answer as for an unknown record.
        if record.initiated_by != user_id and not self._has_entry_for(
            record=record, user_id=user_id
        ):
            raise NotFoundError("入库记录不存在", code=ErrorCode.IMPORT_NOT_FOUND)
        return record

    def _has_entry_for(self, *, record: PaperImport, user_id: UUID) -> bool:
        if record.paper_id is None:
            return False
        session = self._session_factory()
        try:
            return (
                PaperRepository(session).get_user_paper_for_paper(
                    user_id=user_id,
                    paper_id=record.paper_id,
                )
                is not None
            )
        finally:
            session.close()

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
    def acquire(self, import_id: UUID) -> UUID | None:
        """Fetch the source file and record the paper it belongs to.

        Runs inside the worker so a slow download never holds a request open.
        Returns the paper id, or ``None`` when no source could be found; the
        caller records the failure on the stage.
        """
        session = self._session_factory()
        try:
            repository = ImportRepository(session)
            record = repository.get(import_id)
            if record is None:
                return None
            identifier = parse_identifier(record.identifier)

            papers = PaperRepository(session)
            library = self._build_library_service(session, papers)

            # A versioned arXiv id names exactly one file, so a stored copy is
            # the same file and never needs downloading again.
            reused = self._reuse_stored_paper(papers, identifier)
            if reused is not None:
                repository.bind_paper(import_id, reused)
                self._open_entry(papers, record.initiated_by, reused, identifier)
                repository.commit()
                logger.info(
                    "service.import.reused_stored_file",
                    import_id=str(import_id),
                    paper_id=str(reused),
                )
                return reused

            attempted: set[str] = set()
            last_error = str(ErrorCode.PAPER_PDF_NOT_AVAILABLE)
            paper: Paper | None = None
            # The download lives in a temp directory that must outlive the
            # hand-off into storage, so the context is entered here.
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
                            last_error = str(exc.code)
                    stored = self._download_first(
                        urls=fallback,
                        attempted=attempted,
                        destination=staging,
                    )
                if stored is not None:
                    with stored.path.open("rb") as handle:
                        paper = library.adopt_source(
                            stream=handle,
                            filename=f"{identifier.value}.pdf",
                        )

            if paper is None:
                # The stage records the failure; the import is not failed yet,
                # it simply has no source (a distinct terminal state).
                logger.info(
                    "service.import.source_unavailable",
                    import_id=str(import_id),
                    error_code=last_error,
                )
                raise AppError(
                    "没有可用的原文来源",
                    code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                    status_code=422,
                    details={"error_code": last_error},
                )

            # The identifier is part of the paper's identity, not just of the
            # request that fetched it.
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
            repository.bind_paper(import_id, paper.id)
            self._open_entry(papers, record.initiated_by, paper.id, identifier)
            repository.commit()
            logger.info(
                "service.import.bound",
                import_id=str(import_id),
                paper_id=str(paper.id),
            )
            return paper.id
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
