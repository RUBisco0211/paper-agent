"""Import use case: resolve an identifier, then try to get the full text.

Metadata success already produces a usable library entry; a missing or failed
PDF download only marks the entry as waiting for full text.
"""

import asyncio
import tempfile
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import structlog

from ..library.application import PaperLibraryService
from ..library.domain import PaperSource
from ..library.persistence import PaperRepository
from ..platform.database import SessionFactory
from ..platform.errors import AppError, ErrorCode, NotFoundError
from ..platform.storage import ObjectStorage
from ..platform.tasks import TaskScheduler
from ..projects.persistence import ProjectRepository
from ..scholar.identifiers import Identifier, IdentifierType, parse_identifier
from ..scholar.metadata import MetadataResolver
from ..scholar.pdf_fetch import PdfFetcher
from .domain import ImportStatus, PaperImport
from .persistence import ImportRepository

logger = structlog.get_logger(__name__)

IngestionStarterFactory = Callable[..., object]


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
