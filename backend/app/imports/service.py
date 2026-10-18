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
from app.literature_support.scholar.pdf_fetch import PdfFetcher

from ..library.domain import PaperSource
from ..library.repo import PaperRepository
from ..library.service import PaperLibraryService
from ..platform.database import SessionFactory
from ..platform.errors import (
    AppError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from ..platform.security import create_candidate_token, read_candidate_token
from ..platform.storage import ObjectStorage
from ..platform.tasks import TaskScheduler
from ..projects.repo import ProjectRepository
from ..sessions.repo import SessionBindingRepository
from ..sessions.service import SessionBindingService
from .domain import ImportStatus, PaperImport
from .ports import IngestionStarterFactory, PaperDiscoveryAdapter, PdfSourceLocator
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
                        project_id=binding.project_id,
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
    """Starts and reports identifier imports."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        storage: ObjectStorage,
        resolver: MetadataResolver,
        pdf_fetcher: PdfFetcher,
        pdf_locator: PdfSourceLocator,
        scheduler: TaskScheduler,
        ingestion_starter_factory: IngestionStarterFactory,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._resolver = resolver
        self._pdf_fetcher = pdf_fetcher
        self._pdf_locator = pdf_locator
        self._scheduler = scheduler
        self._ingestion_starter_factory = ingestion_starter_factory

    # API surface -----------------------------------------------------------
    def start(
        self,
        *,
        user_id: UUID,
        identifier_text: str,
        project_id: UUID | None = None,
    ) -> PaperImport:
        identifier = parse_identifier(identifier_text)
        session = self._session_factory()
        try:
            if project_id is not None:
                project = ProjectRepository(session).get_project(project_id)
                if project is None or project.user_id != user_id:
                    raise NotFoundError(
                        "项目不存在",
                        code=ErrorCode.PROJECT_NOT_FOUND,
                    )
            repository = ImportRepository(session)
            record = repository.add(
                user_id=user_id,
                identifier_type=identifier.type.value,
                identifier=identifier.value,
                project_id=project_id,
            )
            repository.commit()
            import_id = record.id
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

    def get(self, *, user_id: UUID, import_id: UUID) -> PaperImport:
        session = self._session_factory()
        try:
            record = ImportRepository(session).get(import_id)
        finally:
            session.close()
        if record is None or record.user_id != user_id:
            raise NotFoundError("导入任务不存在", code=ErrorCode.IMPORT_NOT_FOUND)
        return record

    def queue(self, *, user_id: UUID, limit: int = 100) -> list[dict]:
        with self._session_factory() as session:
            imports = ImportRepository(session).list_for_user(
                user_id=user_id, limit=limit
            )
            library = self._build_library_service(session, PaperRepository(session))
            entries, _ = library.list_entries(user_id=user_id, limit=limit, offset=0)
            items: list[dict] = []
            entries_by_id = {entry.user_paper.id: entry for entry in entries}
            imported_papers = {
                item.user_paper_id for item in imports if item.user_paper_id
            }
            for item in imports:
                entry = (
                    entries_by_id.get(item.user_paper_id)
                    if item.user_paper_id is not None
                    else None
                )
                job = entry.latest_job if entry else None
                items.append(
                    {
                        "id": str(item.id),
                        "kind": "import",
                        "identifier": item.identifier,
                        "title": entry.user_paper.title if entry else None,
                        "paper_id": str(item.user_paper_id)
                        if item.user_paper_id
                        else None,
                        "status": job.status.value if job else item.status.value,
                        "stage": (
                            job.current_stage.value
                            if job and job.current_stage
                            else None
                        ),
                        "created_at": item.created_at.isoformat(),
                        "error_code": job.error_code if job else item.error_code,
                    }
                )
            for entry in entries:
                job = entry.latest_job
                if job is None or entry.user_paper.id in imported_papers:
                    continue
                items.append(
                    {
                        "id": str(job.id),
                        "kind": "processing",
                        "title": entry.user_paper.title,
                        "paper_id": str(entry.user_paper.id),
                        "status": job.status.value,
                        "stage": job.current_stage.value if job.current_stage else None,
                        "created_at": job.created_at.isoformat(),
                        "error_code": job.error_code,
                    }
                )
            items.sort(key=lambda item: item["created_at"], reverse=True)
            return items[:limit]

    # Work ------------------------------------------------------------------
    async def _run(self, import_id: UUID) -> None:
        await asyncio.to_thread(self._run_sync, import_id)

    def _run_sync(self, import_id: UUID) -> None:
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
                repository.mark_status(
                    import_id,
                    status=ImportStatus.FAILED,
                    error_code=str(exc.code),
                )
                repository.commit()
                return

            repository.mark_status(import_id, status=ImportStatus.RESOLVING)
            repository.commit()

            outcome = self._resolver.resolve(identifier)
            if outcome.metadata is None:
                repository.mark_status(
                    import_id,
                    status=ImportStatus.FAILED,
                    error_code=str(
                        outcome.error_code or ErrorCode.IDENTIFIER_NOT_RESOLVED
                    ),
                    metadata_source=outcome.source,
                )
                repository.commit()
                logger.info(
                    "service.import.metadata_failed",
                    import_id=str(import_id),
                    error_code=str(outcome.error_code),
                )
                return

            papers = PaperRepository(session)
            user_paper = self._upsert_entry(
                papers,
                user_id=record.user_id,
                identifier=identifier,
                outcome=outcome,
            )
            repository.mark_status(
                import_id,
                status=ImportStatus.METADATA_READY,
                metadata_source=outcome.source,
                user_paper_id=user_paper.id,
            )
            if record.project_id is not None:
                ProjectRepository(session).add_papers(
                    project_id=record.project_id,
                    user_paper_ids=[user_paper.id],
                )
            repository.commit()

            library = self._build_library_service(session, papers)
            attempted: set[str] = set()
            last_error = ErrorCode.PAPER_PDF_NOT_AVAILABLE
            primary_urls = (
                [outcome.metadata.pdf_url] if outcome.metadata.pdf_url else []
            )
            downloaded, error = self._try_pdf_urls(
                library,
                urls=primary_urls,
                attempted=attempted,
                user_id=record.user_id,
                user_paper_id=user_paper.id,
                filename=outcome.metadata.title or f"{identifier.value}.pdf",
                repository=repository,
            )
            if error is not None:
                last_error = error

            if not downloaded and identifier.type is IdentifierType.DOI:
                try:
                    fallback_urls = self._pdf_locator.find(identifier.value)
                except AppError as exc:
                    fallback_urls = []
                    if not attempted:
                        last_error = exc.code
                downloaded, error = self._try_pdf_urls(
                    library,
                    urls=fallback_urls,
                    attempted=attempted,
                    user_id=record.user_id,
                    user_paper_id=user_paper.id,
                    filename=outcome.metadata.title or f"{identifier.value}.pdf",
                    repository=repository,
                )
                if error is not None:
                    last_error = error

            if not downloaded:
                repository.expire_all()
                self._finish(
                    repository,
                    import_id,
                    status=ImportStatus.PDF_UNAVAILABLE,
                    error_code=str(last_error),
                )
                return

            repository.expire_all()
            self._finish(repository, import_id, status=ImportStatus.READY)
            logger.info(
                "service.import.completed",
                import_id=str(import_id),
                user_paper_id=str(user_paper.id),
            )
        except Exception as exc:
            logger.exception(
                "service.import.crashed",
                import_id=str(import_id),
                error_type=type(exc).__name__,
            )
            if repository is None:
                raise
            try:
                repository.mark_status(
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
    def _try_pdf_urls(
        self,
        library: PaperLibraryService,
        *,
        urls: list[str],
        attempted: set[str],
        user_id: UUID,
        user_paper_id: UUID,
        filename: str,
        repository: ImportRepository,
    ) -> tuple[bool, str | None]:
        last_error: str | None = None
        for url in urls:
            if url in attempted:
                continue
            attempted.add(url)
            try:
                self._attach_pdf_from_url(
                    library,
                    url=url,
                    user_id=user_id,
                    user_paper_id=user_paper_id,
                    filename=filename,
                )
            except AppError as exc:
                last_error = exc.code
                repository.expire_all()
            else:
                return True, None
        return False, last_error

    def _attach_pdf_from_url(
        self,
        library: PaperLibraryService,
        *,
        url: str,
        user_id: UUID,
        user_paper_id: UUID,
        filename: str,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="paper-agent-import-") as directory:
            destination = Path(directory) / "download.pdf"
            downloaded = self._pdf_fetcher.download(url, destination=destination)
            with downloaded.path.open("rb") as handle:
                library.attach_pdf(
                    user_id=user_id,
                    user_paper_id=user_paper_id,
                    filename=filename,
                    stream=handle,
                )

    def _upsert_entry(
        self,
        papers: PaperRepository,
        *,
        user_id: UUID,
        identifier: Identifier,
        outcome,
    ):
        """Reuse the user's entry for the same identifier, or create one."""
        metadata = outcome.metadata
        doi = metadata.doi or (
            identifier.value if identifier.type is IdentifierType.DOI else None
        )
        arxiv_id = metadata.arxiv_id or (
            identifier.value if identifier.type is IdentifierType.ARXIV else None
        )
        existing = papers.find_user_paper_by_identifier(
            user_id=user_id,
            doi=doi,
            arxiv_id=arxiv_id,
        )
        if existing is not None:
            updated = papers.update_user_paper_metadata(
                existing.id,
                title=existing.title or metadata.title,
                authors=existing.authors or metadata.authors,
                abstract=existing.abstract or metadata.abstract,
                doi=existing.doi or doi,
                arxiv_id=existing.arxiv_id or arxiv_id,
                year=existing.year or metadata.year,
                venue=existing.venue or metadata.venue,
                bibliographic=metadata.bibliographic(),
                metadata_status=metadata.metadata_status(),
                metadata_sources=existing.metadata_sources
                or [
                    {
                        "field": identifier.type.value,
                        "source": outcome.source,
                        "value": identifier.value,
                    },
                ],
            )
            assert updated is not None
            logger.info(
                "service.import.entry_reused",
                user_paper_id=str(existing.id),
            )
            return updated

        return papers.add_user_paper(
            user_id=user_id,
            paper_id=None,
            title=metadata.title,
            source=(
                PaperSource.DOI
                if identifier.type is IdentifierType.DOI
                else PaperSource.ARXIV
            ),
            doi=doi,
            arxiv_id=arxiv_id,
            authors=metadata.authors,
            abstract=metadata.abstract,
            year=metadata.year,
            venue=metadata.venue,
            bibliographic=metadata.bibliographic(),
            metadata_status=metadata.metadata_status(),
            metadata_sources=[
                {
                    "field": identifier.type.value,
                    "source": outcome.source,
                    "value": identifier.value,
                },
            ],
        )

    def _build_library_service(self, session, papers: PaperRepository):
        ingestion = self._ingestion_starter_factory(
            session=session,
            storage=self._storage,
            session_factory=self._session_factory,
            scheduler=self._scheduler,
        )
        return PaperLibraryService(
            papers,
            ingestion,
            self._storage,
            self._resolver,
            self._pdf_fetcher,
        )

    def _finish(
        self,
        repository: ImportRepository,
        import_id: UUID,
        *,
        status: ImportStatus,
        error_code: str | None = None,
    ) -> None:
        repository.mark_status(import_id, status=status, error_code=error_code)
        repository.commit()
