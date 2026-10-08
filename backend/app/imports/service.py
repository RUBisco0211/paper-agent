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
from ..platform.security import read_candidate_token
from ..platform.storage import ObjectStorage
from ..platform.tasks import TaskScheduler
from ..projects.repo import ProjectRepository
from ..scholar.identifiers import Identifier, IdentifierType, parse_identifier
from ..scholar.metadata import MetadataResolver
from ..scholar.pdf_fetch import PdfFetcher
from ..sessions.repo import SessionBindingRepository
from ..sessions.service import SessionBindingService
from .domain import ImportStatus, PaperImport
from .ports import IngestionStarterFactory
from .repo import ImportApprovalRecord, ImportRepository

logger = structlog.get_logger(__name__)


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
            openalex_id = claims.get("oid")
            if not isinstance(openalex_id, str) or not openalex_id.startswith(
                "https://openalex.org/W"
            ):
                raise ValidationError("候选文献信息无效")
            if identifier.value in seen:
                continue
            seen.add(identifier.value)
            candidates.append(
                {"identifier": identifier.value, "openalex_id": openalex_id}
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


class ImportService:
    """Starts and reports identifier imports."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        storage: ObjectStorage,
        resolver: MetadataResolver,
        pdf_fetcher: PdfFetcher,
        scheduler: TaskScheduler,
        ingestion_starter_factory: IngestionStarterFactory,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._resolver = resolver
        self._pdf_fetcher = pdf_fetcher
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
                entry = entries_by_id.get(item.user_paper_id)
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

            if not outcome.metadata.pdf_url:
                self._finish(
                    repository,
                    import_id,
                    status=ImportStatus.PDF_UNAVAILABLE,
                    error_code=str(ErrorCode.PAPER_PDF_NOT_AVAILABLE),
                )
                return

            library = self._build_library_service(session, papers)
            try:
                with tempfile.TemporaryDirectory(
                    prefix="paper-agent-import-"
                ) as directory:
                    destination = Path(directory) / "download.pdf"
                    downloaded = self._pdf_fetcher.download(
                        outcome.metadata.pdf_url,
                        destination=destination,
                    )
                    with downloaded.path.open("rb") as handle:
                        library.attach_pdf(
                            user_id=record.user_id,
                            user_paper_id=user_paper.id,
                            filename=outcome.metadata.title
                            or f"{identifier.value}.pdf",
                            stream=handle,
                        )
            except AppError as exc:
                # Metadata stays; the user can retry or upload the PDF later.
                repository.expire_all()
                self._finish(
                    repository,
                    import_id,
                    status=ImportStatus.PDF_UNAVAILABLE,
                    error_code=str(exc.code),
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
