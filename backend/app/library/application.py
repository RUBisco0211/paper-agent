import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import structlog

from ..ingestion.domain import IngestionJob
from ..platform.config import settings as app_settings
from ..platform.errors import AppError, ErrorCode
from ..platform.storage import ObjectStorage, paper_pdf_key
from .domain import (
    Capabilities,
    Paper,
    PaperSource,
    UserPaper,
    placeholder_title_from_filename,
)
from .pdf import ensure_pdf_magic, inspect_pdf
from .persistence import PaperRepository
from .ports import IngestionStarter

logger = structlog.get_logger(__name__)

CHUNK_SIZE = 1024 * 1024
MAX_FILENAME_LENGTH = 512


@dataclass(frozen=True, slots=True)
class LibraryEntry:
    """Everything the API needs to describe one user-visible paper entry."""

    user_paper: UserPaper
    paper: Paper | None
    capabilities: Capabilities
    latest_job: IngestionJob | None


@dataclass(frozen=True, slots=True)
class StoredPdf:
    file_hash: str
    byte_size: int
    page_count: int
    storage_key: str


class PaperLibraryService:
    """Use cases for the personal paper library."""

    def __init__(
        self,
        papers: PaperRepository,
        ingestion: IngestionStarter,
        storage: ObjectStorage,
        *,
        max_pdf_bytes: int | None = None,
        max_pdf_pages: int | None = None,
    ) -> None:
        self._papers = papers
        self._ingestion = ingestion
        self._storage = storage
        self._max_pdf_bytes = max_pdf_bytes or app_settings.max_pdf_bytes
        self._max_pdf_pages = max_pdf_pages or app_settings.max_pdf_pages

    # Uploads ---------------------------------------------------------------
    def upload_pdf(
        self,
        *,
        user_id: UUID,
        filename: str | None,
        stream: BinaryIO,
    ) -> tuple[LibraryEntry, IngestionJob | None]:
        stored = self._store_pdf(stream)
        paper = self._papers.get_paper_by_hash(stored.file_hash)
        if paper is None:
            paper = self._papers.add_paper(
                file_hash=stored.file_hash,
                byte_size=stored.byte_size,
                page_count=stored.page_count,
            )
            logger.info(
                "service.library.paper_created",
                paper_id=str(paper.id),
                file_hash=stored.file_hash,
            )

        user_paper = self._papers.get_user_paper_for_paper(
            user_id=user_id,
            paper_id=paper.id,
        )
        if user_paper is None:
            user_paper = self._papers.add_user_paper(
                user_id=user_id,
                paper_id=paper.id,
                title=placeholder_title_from_filename(filename),
                source=PaperSource.UPLOAD,
                original_filename=_truncate(filename),
            )
            logger.info(
                "service.library.entry_created",
                user_id=str(user_id),
                user_paper_id=str(user_paper.id),
            )

        job = self._ingestion.start_for_paper(paper.id)
        self._papers.commit()
        entry = self.get_entry(user_id=user_id, user_paper_id=user_paper.id)
        assert entry is not None
        return entry, job

    def get_pdf_stream(self, *, user_id: UUID, user_paper_id: UUID) -> BinaryIO:
        entry = self.get_entry(user_id=user_id, user_paper_id=user_paper_id)
        if entry is None:
            raise AppError(
                "论文不存在", code=ErrorCode.PAPER_NOT_FOUND, status_code=404
            )
        if entry.paper is None:
            raise AppError(
                "该条目还没有可用的 PDF",
                code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                status_code=404,
            )
        key = paper_pdf_key(entry.paper.file_hash)
        if not self._storage.exists(key):
            raise AppError(
                "PDF 文件已不可用",
                code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                status_code=404,
            )
        return self._storage.open(key)

    # Queries ---------------------------------------------------------------
    def list_entries(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> tuple[list[LibraryEntry], int]:
        user_papers, total = self._papers.list_user_papers(
            user_id=user_id,
            limit=limit,
            offset=offset,
            query=query,
        )
        return self._with_related(user_papers), total

    def get_entry(self, *, user_id: UUID, user_paper_id: UUID) -> LibraryEntry | None:
        user_paper = self._papers.get_user_paper(user_paper_id)
        if user_paper is None or user_paper.user_id != user_id:
            return None
        return self._with_related([user_paper])[0]

    # Internals -------------------------------------------------------------
    def _with_related(self, user_papers: list[UserPaper]) -> list[LibraryEntry]:
        paper_ids = [
            user_paper.paper_id
            for user_paper in user_papers
            if user_paper.paper_id is not None
        ]
        papers = {
            paper_id: paper
            for paper_id in paper_ids
            if (paper := self._papers.get_paper(paper_id)) is not None
        }
        jobs = self._ingestion.latest_jobs_for_papers(paper_ids)

        return [
            LibraryEntry(
                user_paper=user_paper,
                paper=papers.get(user_paper.paper_id) if user_paper.paper_id else None,
                capabilities=user_paper.capabilities(
                    papers.get(user_paper.paper_id) if user_paper.paper_id else None,
                ),
                latest_job=jobs.get(user_paper.paper_id)
                if user_paper.paper_id
                else None,
            )
            for user_paper in user_papers
        ]

    def _store_pdf(self, stream: BinaryIO) -> StoredPdf:
        """Stream an untrusted upload to storage after validating it."""
        hasher = hashlib.sha256()
        byte_size = 0
        magic = b""
        with tempfile.TemporaryDirectory(prefix="paper-agent-upload-") as directory:
            temporary_path = Path(directory) / "upload.pdf"
            with temporary_path.open("wb") as handle:
                while chunk := stream.read(CHUNK_SIZE):
                    if not magic:
                        magic = chunk[: len(b"%PDF-")]
                    byte_size += len(chunk)
                    if byte_size > self._max_pdf_bytes:
                        raise AppError(
                            "PDF 超过大小上限",
                            code=ErrorCode.PDF_TOO_LARGE,
                            status_code=413,
                        )
                    hasher.update(chunk)
                    handle.write(chunk)

            ensure_pdf_magic(magic)
            inspection = inspect_pdf(temporary_path, max_pages=self._max_pdf_pages)
            file_hash = hasher.hexdigest()
            key = paper_pdf_key(file_hash)
            if not self._storage.exists(key):
                with temporary_path.open("rb") as source:
                    self._storage.write_chunks(
                        key, iter(lambda: source.read(CHUNK_SIZE), b"")
                    )

        return StoredPdf(
            file_hash=file_hash,
            byte_size=byte_size,
            page_count=inspection.page_count,
            storage_key=key,
        )


def _truncate(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:MAX_FILENAME_LENGTH]
