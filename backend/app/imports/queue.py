"""Start, inspect and retry the import that brings a paper into the library."""

from uuid import UUID

import structlog

from ..library.domain import Paper, PaperSource
from ..library.repo import PaperRepository
from ..platform.errors import ConflictError, ErrorCode, NotFoundError
from .domain import (
    ACTIVE_STATUSES,
    ImportStage,
    ImportStatus,
    PaperImport,
    source_of,
)
from .ports import ImportRunner
from .repo import ImportRepository

logger = structlog.get_logger(__name__)


class ImportQueueService:
    """Queue one import per paper and report its stage state."""

    def __init__(
        self,
        repository: ImportRepository,
        papers: PaperRepository,
        runner: ImportRunner | None = None,
    ) -> None:
        self._repository = repository
        self._papers = papers
        self._runner = runner

    def user_paper_id(self, *, paper_id: UUID, user_id: UUID) -> UUID:
        """Map a shared paper to the requesting user's own entry id."""
        user_paper = self._papers.get_user_paper_for_paper(
            user_id=user_id,
            paper_id=paper_id,
        )
        if user_paper is None:
            # Same code as an unknown import: an import on another user's paper
            # must not reveal that the paper or the import exists.
            raise NotFoundError(
                "入库记录不存在",
                code=ErrorCode.IMPORT_NOT_FOUND,
            )
        return user_paper.id

    def start_for_paper(
        self,
        paper: Paper,
        *,
        initiated_by: UUID,
        identifier_type: str,
        identifier: str,
    ) -> PaperImport:
        """Queue the import a stored paper needs, reusing its single record.

        A paper that already finished returns immediately, so re-uploading the
        same file never re-parses it; a record that is no longer ready means an
        artifact went missing and the whole flow runs again.
        """
        # Only an identifier-based import can be recognised again by its
        # identifier; an upload is identified by the file it stored.
        existing = self._repository.find_by_paper(paper.id)
        if existing is None and identifier_type != "upload":
            existing = self._repository.find_by_identifier(
                identifier_type=identifier_type,
                identifier=identifier,
            )

        if existing is None:
            record = self._repository.add(
                initiated_by=initiated_by,
                identifier_type=identifier_type,
                identifier=identifier,
            )
            self._repository.bind_paper(record.id, paper.id)
            import_id = record.id
            # The file is already stored, so the entry can exist from now on;
            # it stays out of the library until the stages finish.
            self._papers.link_paper(
                user_id=initiated_by,
                paper_id=paper.id,
                source=source_of(identifier_type),
            )
            self._papers.commit()
        else:
            import_id = existing.id
            if existing.status is ImportStatus.READY:
                # The paper is already usable: the second person only needs
                # their own entry, not a new import.
                self._link_if_ready(existing, initiated_by)
                return existing
            if existing.status in ACTIVE_STATUSES:
                # Someone else's import is still running; this user joins it by
                # getting their own entry, which is revealed when it finishes.
                self._papers.link_paper(
                    user_id=initiated_by,
                    paper_id=paper.id,
                    source=source_of(identifier_type),
                )
                self._papers.commit()
                return existing
            self._repository.bind_paper(import_id, paper.id)
            self._papers.link_paper(
                user_id=initiated_by,
                paper_id=paper.id,
                source=source_of(identifier_type),
            )
            self._papers.commit()
            self._repository.reset_for_retry(import_id)
            self._repository.commit()

        # The file is already stored by the time an import reaches the queue,
        # whichever way it arrived, so the source stage is done.
        self._repository.mark_stage_succeeded(
            import_id,
            stage=ImportStage.SOURCE,
            progress={"stored": True},
        )
        self._repository.commit()

        logger.info(
            "import.queued",
            import_id=str(import_id),
            paper_id=str(paper.id),
        )
        if self._runner is not None:
            self._runner.submit(import_id)
            self._repository.expire_all()
        started = self._repository.get(import_id)
        assert started is not None
        return started

    def _link_if_ready(self, record: PaperImport, user_id: UUID) -> None:
        paper_id = record.paper_id
        if paper_id is None:
            return
        if self._papers.get_user_paper_for_paper(
            user_id=user_id,
            paper_id=record.paper_id,
        ) is not None:
            return
        self._papers.add_user_paper(
            user_id=user_id,
            paper_id=paper_id,
            source=source_of(record.identifier_type),
            ready=True,
        )
        self._papers.commit()

    def retry(self, import_id: UUID) -> PaperImport:
        record = self._repository.get(import_id)
        if record is None:
            raise NotFoundError("入库记录不存在", code=ErrorCode.IMPORT_NOT_FOUND)
        if record.status in ACTIVE_STATUSES:
            raise ConflictError(
                "该文献仍在入库中",
                code=ErrorCode.IMPORT_ALREADY_RUNNING,
            )
        self._repository.reset_for_retry(import_id)
        self._repository.commit()
        logger.info("import.retried", import_id=str(import_id))
        if self._runner is not None:
            self._runner.submit(import_id)
            self._repository.expire_all()
        retried = self._repository.get(import_id)
        assert retried is not None
        return retried

    def get(self, import_id: UUID) -> PaperImport | None:
        return self._repository.get(import_id)

    def latest_imports_for_papers(
        self,
        paper_ids: list[UUID],
    ) -> dict[UUID, PaperImport]:
        found: dict[UUID, PaperImport] = {}
        for paper_id in paper_ids:
            record = self._repository.find_by_paper(paper_id)
            if record is not None:
                found[paper_id] = record
        return found


