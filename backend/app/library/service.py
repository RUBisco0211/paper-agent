import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import structlog

from app.literature_support.importing.blocks import (
    build_block_index,
    normalize_image_path,
)
from app.literature_support.importing.pdf import ensure_pdf_magic, inspect_pdf
from app.literature_support.importing.text import detect_identifiers
from app.literature_support.scholar.identifiers import Identifier
from app.pipelines.domain import Run

from ..platform.config import settings as app_settings
from ..platform.errors import AppError, ErrorCode, NotFoundError
from ..platform.storage import ObjectStorage, paper_pdf_key
from .domain import (
    Capabilities,
    Paper,
    UserPaper,
)
from .ports import MetadataEnricherPort, RunStarter
from .repo import PaperRepository

logger = structlog.get_logger(__name__)

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class LibraryEntry:
    """Everything the API needs to describe one user-visible paper entry."""

    user_paper: UserPaper
    paper: Paper | None
    capabilities: Capabilities
    latest_run: Run | None


@dataclass(frozen=True, slots=True)
class StoredPdf:
    file_hash: str
    byte_size: int
    page_count: int
    storage_key: str
    detected_identifiers: tuple[Identifier, ...] = ()


class PaperLibraryService:
    """Use cases for the personal paper library."""

    def __init__(
        self,
        papers: PaperRepository,
        runs: RunStarter,
        enrichment: MetadataEnricherPort,
        storage: ObjectStorage,
        *,
        max_pdf_bytes: int | None = None,
        max_pdf_pages: int | None = None,
    ) -> None:
        self._papers = papers
        self._runs = runs
        self._enrichment = enrichment
        self._storage = storage
        self._max_pdf_bytes = max_pdf_bytes or app_settings.max_pdf_bytes
        self._max_pdf_pages = max_pdf_pages or app_settings.max_pdf_pages

    # Uploads ---------------------------------------------------------------
    def list_blocks(
        self,
        *,
        user_id: UUID,
        user_paper_id: UUID,
        block_type: str | None,
        offset: int,
        limit: int,
    ) -> dict:
        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        paper = entry.paper
        if paper is None or not paper.artifact_manifest_key:
            return {
                "types": [],
                "items": [],
                "total": 0,
                "offset": offset,
                "limit": limit,
            }
        try:
            if paper.artifact_manifest_key:
                manifest = json.loads(
                    self._storage.read_text(paper.artifact_manifest_key)
                )
                if manifest.get("file_hash") != paper.file_hash:
                    raise ValueError("artifact hash mismatch")
                files = manifest["files"]
                part = files.get("blocks_index.json") or files["content_list.json"]
                raw = self._read_artifact_part(part)
                payload = json.loads(raw)
                index = (
                    payload
                    if "blocks_index.json" in files
                    else build_block_index(payload)
                )
                if index.get("schema_version", 0) < 2 and "content_list.json" in files:
                    original = self._read_artifact_part(files["content_list.json"])
                    index = build_block_index(json.loads(original))
            items = index["items"]
            types = index["types"]
        except (KeyError, ValueError, TypeError, FileNotFoundError) as exc:
            raise AppError(
                "文献解析结果不可读取",
                code=ErrorCode.IMPORT_ARTIFACT_INVALID,
                status_code=502,
            ) from exc
        selected = (
            [item for item in items if item["type"] == block_type]
            if block_type
            else items
        )
        return {
            "types": types,
            "items": selected[offset : offset + limit],
            "total": len(selected),
            "offset": offset,
            "limit": limit,
        }

    def get_block(self, *, user_id: UUID, user_paper_id: UUID, block_id: int) -> dict:
        result = self.list_blocks(
            user_id=user_id,
            user_paper_id=user_paper_id,
            block_type=None,
            offset=0,
            limit=1000000,
        )
        for item in result["items"]:
            if item["id"] == block_id:
                return item
        raise NotFoundError("原文片段不存在", code=ErrorCode.PAPER_NOT_FOUND)

    def get_block_full_text(
        self, *, user_id: UUID, user_paper_id: UUID, block_id: int
    ) -> str:
        """Read an original MinerU block for quote verification."""
        from app.literature_support.importing.blocks import block_full_text

        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        paper = entry.paper
        if paper is None:
            raise NotFoundError("原文片段不存在", code=ErrorCode.PAPER_NOT_FOUND)
        if not paper.artifact_manifest_key:
            raise NotFoundError("原文片段不存在", code=ErrorCode.PAPER_NOT_FOUND)
        manifest = json.loads(self._storage.read_text(paper.artifact_manifest_key))
        if manifest.get("file_hash") != paper.file_hash:
            raise ValueError("artifact hash mismatch")
        raw = self._read_artifact_part(manifest["files"]["content_list.json"])
        content = json.loads(raw)
        if not isinstance(content, list) or block_id < 0 or block_id >= len(content):
            raise NotFoundError("原文片段不存在", code=ErrorCode.PAPER_NOT_FOUND)
        return block_full_text(content[block_id])

    def get_block_image(
        self, *, user_id: UUID, user_paper_id: UUID, block_id: int
    ) -> tuple[bytes, str]:
        block = self.get_block(
            user_id=user_id, user_paper_id=user_paper_id, block_id=block_id
        )
        image_path = normalize_image_path(block.get("image_path"))
        if image_path is None:
            raise NotFoundError("片段没有图片预览", code=ErrorCode.PAPER_NOT_FOUND)
        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        paper = entry.paper
        if paper is None:
            raise NotFoundError("图片预览不可用", code=ErrorCode.PAPER_NOT_FOUND)
        manifest_key = paper.artifact_manifest_key
        if not manifest_key:
            raise NotFoundError("图片预览不可用", code=ErrorCode.PAPER_NOT_FOUND)
        try:
            manifest = json.loads(self._storage.read_text(manifest_key))
            if manifest.get("file_hash") != paper.file_hash:
                raise ValueError("artifact hash mismatch")
            files = manifest["files"]
            if image_path in files:
                matches = [files[image_path]]
            else:
                matches = [
                    part
                    for name, part in files.items()
                    if name.endswith(f"/{image_path}")
                ]
            if len(matches) != 1:
                raise NotFoundError("图片预览不可用", code=ErrorCode.PAPER_NOT_FOUND)
            payload = self._read_artifact_part(matches[0])
        except (KeyError, ValueError, TypeError, FileNotFoundError) as exc:
            raise AppError(
                "文献图片不可读取",
                code=ErrorCode.IMPORT_ARTIFACT_INVALID,
                status_code=502,
            ) from exc
        return payload, self._image_media_type(image_path)

    @staticmethod
    def _image_media_type(image_path: str) -> str:
        suffix = image_path.rsplit(".", 1)[-1].lower()
        return "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"

    def _read_artifact_part(self, part: dict) -> bytes:
        raw = self._storage.read_bytes(part["key"])
        if hashlib.sha256(raw).hexdigest() != part["sha256"]:
            raise ValueError("artifact checksum mismatch")
        return raw

    def upload_pdf(
        self,
        *,
        user_id: UUID,
        filename: str | None,
        stream: BinaryIO,
        project_id: UUID | None = None,
    ) -> Run:
        """Store a source file and join it to the paper's processing.

        The file hash decides paper identity, so a file already stored reuses
        its paper. The user joins the paper's active run or starts one; either
        way the library entry appears only when a run succeeds.
        """
        stored = self._store_stream(stream)
        paper = self._papers.get_or_add_paper(
            file_hash=stored.file_hash,
            byte_size=stored.byte_size,
            page_count=stored.page_count,
        )
        self._papers.commit()
        self._enrich_quietly(paper.id, stored.detected_identifiers)
        run = self._runs.request(
            user_id=user_id, paper_id=paper.id, project_id=project_id
        )
        self._papers.expire_all()
        return run

    def _enrich_quietly(
        self,
        paper_id: UUID,
        identifiers: tuple[Identifier, ...] = (),
    ) -> None:
        """Queue the bibliographic lookup; the caller never waits for it."""
        try:
            self._enrichment.submit(paper_id, identifiers)
        except Exception as exc:
            logger.warning(
                "service.library.enrichment_failed",
                paper_id=str(paper_id),
                error_type=type(exc).__name__,
            )

    def pdf_cache_version(self, *, user_id: UUID, user_paper_id: UUID) -> str:
        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        if entry.paper is None:
            raise AppError(
                "该条目还没有可用的 PDF",
                code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                status_code=404,
            )
        if not self._storage.exists(paper_pdf_key(entry.paper.file_hash)):
            raise AppError(
                "PDF 文件已不可用",
                code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                status_code=404,
            )
        return entry.paper.file_hash

    def artifact_cache_version(
        self, *, user_id: UUID, user_paper_id: UUID
    ) -> str | None:
        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        paper = entry.paper
        if paper is None or not paper.artifact_manifest_key:
            return None
        version = paper.artifact_manifest_key
        return f"{paper.file_hash}:{version}"

    def get_pdf_stream(self, *, user_id: UUID, user_paper_id: UUID) -> BinaryIO:
        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
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

    def entries_for(
        self,
        *,
        user_id: UUID,
        user_paper_ids: list[UUID],
    ) -> list[LibraryEntry]:
        """Project a set of entries with their papers and latest jobs."""
        user_papers = self._papers.user_papers_by_ids(
            user_id=user_id,
            user_paper_ids=user_paper_ids,
        )
        by_id = {user_paper.id: user_paper for user_paper in user_papers}
        ordered = [
            by_id[user_paper_id]
            for user_paper_id in user_paper_ids
            if user_paper_id in by_id
        ]
        return self._with_related(ordered)

    def get_entry(self, *, user_id: UUID, user_paper_id: UUID) -> LibraryEntry | None:
        user_paper = self._papers.get_user_paper(user_paper_id)
        if user_paper is None or user_paper.user_id != user_id:
            return None
        return self._with_related([user_paper])[0]

    # Internals -------------------------------------------------------------
    def _require_entry(self, *, user_id: UUID, user_paper_id: UUID) -> LibraryEntry:
        entry = self.get_entry(user_id=user_id, user_paper_id=user_paper_id)
        if entry is None:
            raise NotFoundError("论文不存在", code=ErrorCode.PAPER_NOT_FOUND)
        return entry

    def adopt_source(
        self,
        *,
        stream: BinaryIO,
        filename: str | None,
    ) -> Paper:
        """Store a source file and return its paper, without starting a run.

        The download owns the request that carries this file, so it must not
        open a second path into the run by going through the upload entry point.
        """
        stored = self._store_stream(stream)
        paper = self._papers.get_or_add_paper(
            file_hash=stored.file_hash,
            byte_size=stored.byte_size,
            page_count=stored.page_count,
        )
        self._papers.commit()
        # Look the bibliographic facts up beside the run, never inside it.
        self._enrich_quietly(paper.id, stored.detected_identifiers)
        return paper

    def link_entry(self, *, user_id: UUID, paper_id: UUID) -> UserPaper:
        """Add a ready paper to the user's library, or return the existing link."""
        existing = self._papers.get_user_paper_for_paper(
            user_id=user_id,
            paper_id=paper_id,
        )
        if existing is not None:
            return existing
        created = self._papers.add_user_paper(user_id=user_id, paper_id=paper_id)
        logger.info(
            "service.library.entry_created",
            user_id=str(user_id),
            user_paper_id=str(created.id),
        )
        return created

    def _with_related(self, user_papers: list[UserPaper]) -> list[LibraryEntry]:
        paper_ids = [user_paper.paper_id for user_paper in user_papers]
        papers = {
            paper_id: paper
            for paper_id in paper_ids
            if (paper := self._papers.get_paper(paper_id)) is not None
        }
        runs = self._runs.latest_for_papers(paper_ids)

        return [
            LibraryEntry(
                user_paper=user_paper,
                paper=papers.get(user_paper.paper_id),
                capabilities=user_paper.capabilities(
                    papers.get(user_paper.paper_id),
                ),
                latest_run=runs.get(user_paper.paper_id),
            )
            for user_paper in user_papers
        ]

    def _digest(
        self,
        source: BinaryIO,
        sink: BinaryIO | None = None,
    ) -> tuple[str, int]:
        """Hash and size-check a PDF, optionally copying it to ``sink``."""
        hasher = hashlib.sha256()
        byte_size = 0
        magic = b""
        while chunk := source.read(CHUNK_SIZE):
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
            if sink is not None:
                sink.write(chunk)
        ensure_pdf_magic(magic)
        return hasher.hexdigest(), byte_size

    def _store_stream(self, stream: BinaryIO) -> StoredPdf:
        with tempfile.TemporaryDirectory(prefix="paper-agent-upload-") as directory:
            temporary_path = Path(directory) / "upload.pdf"
            with temporary_path.open("wb") as handle:
                file_hash, byte_size = self._digest(stream, handle)
            return self._finalize(temporary_path, file_hash, byte_size)

    def _store_path(self, path: Path) -> StoredPdf:
        with path.open("rb") as handle:
            file_hash, byte_size = self._digest(handle)
        return self._finalize(path, file_hash, byte_size)

    def _finalize(
        self,
        temporary_path: Path,
        file_hash: str,
        byte_size: int,
    ) -> StoredPdf:
        inspection = inspect_pdf(temporary_path, max_pages=self._max_pdf_pages)
        detected = tuple(detect_identifiers(temporary_path))
        key = paper_pdf_key(file_hash)
        if not self._storage.exists(key):
            with temporary_path.open("rb") as source:
                self._storage.write_chunks(
                    key,
                    iter(lambda: source.read(CHUNK_SIZE), b""),
                )
        return StoredPdf(
            file_hash=file_hash,
            byte_size=byte_size,
            page_count=inspection.page_count,
            storage_key=key,
            detected_identifiers=detected,
        )
