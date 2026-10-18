import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import structlog

from app.literature_support.processing.blocks import (
    build_block_index,
    normalize_image_path,
)
from app.literature_support.processing.pdf import ensure_pdf_magic, inspect_pdf
from app.literature_support.processing.text import detect_identifiers
from app.literature_support.scholar.identifiers import (
    Identifier,
    IdentifierType,
    parse_identifier,
)
from app.literature_support.scholar.merge import merge_provider_metadata, merge_sources
from app.literature_support.scholar.metadata import MetadataResolver, ProviderMetadata
from app.literature_support.scholar.pdf_fetch import PdfFetcher
from app.processing.domain import IngestionJob

from ..platform.config import settings as app_settings
from ..platform.errors import AppError, ConflictError, ErrorCode, NotFoundError
from ..platform.storage import ObjectStorage, mineru_artifact_key, paper_pdf_key
from .domain import (
    Capabilities,
    MetadataStatus,
    Paper,
    PaperSource,
    UserPaper,
    placeholder_title_from_filename,
)
from .ports import IngestionStarter
from .repo import PaperRepository

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
    detected_identifiers: tuple[Identifier, ...] = ()


@dataclass(frozen=True, slots=True)
class PaperInfoUpdate:
    """用户在自己的条目上编辑的书目信息（界面「编辑信息」）。"""

    title: str | None = None
    authors: list[str] | None = None
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    year: int | None = None
    venue: str | None = None

    def is_empty(self) -> bool:
        return all(
            getattr(self, name) is None
            for name in (
                "title",
                "authors",
                "abstract",
                "doi",
                "arxiv_id",
                "year",
                "venue",
            )
        )


@dataclass(frozen=True, slots=True)
class MetadataFetchResult:
    """一次在线获取元数据的结果（界面「获取元数据」）。"""

    entry: LibraryEntry
    status: MetadataStatus
    source: str | None = None
    error_code: str | None = None
    applied_fields: tuple[str, ...] = field(default_factory=tuple)
    provider_metadata: ProviderMetadata | None = None


class PaperLibraryService:
    """Use cases for the personal paper library."""

    def __init__(
        self,
        papers: PaperRepository,
        ingestion: IngestionStarter,
        storage: ObjectStorage,
        resolver: MetadataResolver,
        pdf_fetcher: PdfFetcher,
        *,
        max_pdf_bytes: int | None = None,
        max_pdf_pages: int | None = None,
    ) -> None:
        self._papers = papers
        self._ingestion = ingestion
        self._storage = storage
        self._resolver = resolver
        self._pdf_fetcher = pdf_fetcher
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
        if paper is None or not paper.has_fulltext:
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
            else:
                raw = self._storage.read_text(
                    mineru_artifact_key(paper.file_hash, "content_list.json")
                )
                index = build_block_index(json.loads(raw))
            items = index["items"]
            types = index["types"]
        except (KeyError, ValueError, TypeError, FileNotFoundError) as exc:
            raise AppError(
                "文献解析结果不可读取",
                code=ErrorCode.INGESTION_ARTIFACT_INVALID,
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
        from app.literature_support.processing.blocks import block_full_text

        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        paper = entry.paper
        if paper is None:
            raise NotFoundError("原文片段不存在", code=ErrorCode.PAPER_NOT_FOUND)
        if paper.artifact_manifest_key:
            manifest = json.loads(self._storage.read_text(paper.artifact_manifest_key))
            if manifest.get("file_hash") != paper.file_hash:
                raise ValueError("artifact hash mismatch")
            raw = self._read_artifact_part(manifest["files"]["content_list.json"])
            content = json.loads(raw)
        else:
            content = json.loads(
                self._storage.read_text(
                    mineru_artifact_key(paper.file_hash, "content_list.json")
                )
            )
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
            for relative_path in (f"images/{image_path}", image_path):
                key = mineru_artifact_key(paper.file_hash, relative_path)
                if self._storage.exists(key):
                    return self._storage.read_bytes(key), self._image_media_type(
                        image_path
                    )
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
                code=ErrorCode.INGESTION_ARTIFACT_INVALID,
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
    ) -> tuple[LibraryEntry, IngestionJob | None]:
        stored = self._store_stream(stream)
        paper = self._papers.get_or_add_paper(
            file_hash=stored.file_hash,
            byte_size=stored.byte_size,
            page_count=stored.page_count,
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
        return self._finish_write(user_id, user_paper, paper)

    def attach_pdf(
        self,
        *,
        user_id: UUID,
        user_paper_id: UUID,
        filename: str | None,
        stream: BinaryIO,
    ) -> tuple[LibraryEntry, IngestionJob | None]:
        """Attach a manually supplied PDF to an existing entry."""
        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        stored = self._store_stream(stream)
        self._ensure_no_identifier_conflict(entry.user_paper, stored)
        paper = self._papers.get_or_add_paper(
            file_hash=stored.file_hash,
            byte_size=stored.byte_size,
            page_count=stored.page_count,
        )
        self._papers.link_user_paper_to_paper(user_paper_id, paper.id)
        user_paper = self._papers.get_user_paper(user_paper_id)
        assert user_paper is not None
        if user_paper.title is None and filename:
            self._papers.update_user_paper_metadata(
                user_paper_id,
                title=placeholder_title_from_filename(filename),
            )
        return self._finish_write(user_id, user_paper, paper)

    def fetch_pdf(
        self,
        *,
        user_id: UUID,
        user_paper_id: UUID,
    ) -> tuple[LibraryEntry, IngestionJob | None, MetadataFetchResult]:
        """Re-attempt downloading the PDF for a metadata-only entry."""
        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        if entry.paper is not None and entry.capabilities.has_pdf:
            raise ConflictError(
                "该条目已经有 PDF",
                code=ErrorCode.CONFLICT,
            )

        completion = self.fetch_metadata(
            user_id=user_id,
            user_paper_id=user_paper_id,
        )
        metadata = completion.provider_metadata
        if metadata is None or not metadata.pdf_url:
            raise AppError(
                "来源没有提供公开可用的 PDF，请手动上传全文",
                code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                status_code=422,
            )

        with tempfile.TemporaryDirectory(prefix="paper-agent-fetch-") as directory:
            destination = Path(directory) / "download.pdf"
            downloaded = self._pdf_fetcher.download(
                metadata.pdf_url,
                destination=destination,
            )
            stored = self._store_path(downloaded.path)
        self._ensure_no_identifier_conflict(completion.entry.user_paper, stored)

        paper = self._papers.get_or_add_paper(
            file_hash=stored.file_hash,
            byte_size=stored.byte_size,
            page_count=stored.page_count,
        )
        self._papers.link_user_paper_to_paper(user_paper_id, paper.id)
        user_paper = self._papers.get_user_paper(user_paper_id)
        assert user_paper is not None
        entry, job = self._finish_write(user_id, user_paper, paper)
        logger.info(
            "service.library.pdf_fetched",
            user_paper_id=str(user_paper_id),
            source=completion.source,
        )
        return entry, job, completion

    # Metadata --------------------------------------------------------------
    def update_info(
        self,
        *,
        user_id: UUID,
        user_paper_id: UUID,
        update: PaperInfoUpdate,
    ) -> LibraryEntry:
        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        if update.is_empty():
            return entry

        doi = _normalize_doi(update.doi)
        arxiv_id = _normalize_arxiv(update.arxiv_id)
        sources = merge_sources(
            entry.user_paper.metadata_sources,
            [
                field
                for field, value in (
                    ("title", update.title),
                    ("authors", update.authors),
                    ("abstract", update.abstract),
                    ("doi", doi),
                    ("arxiv_id", arxiv_id),
                    ("year", update.year),
                    ("venue", update.venue),
                )
                if value is not None
            ],
        )
        self._papers.update_user_paper_metadata(
            user_paper_id,
            title=update.title,
            authors=update.authors,
            abstract=update.abstract,
            doi=doi,
            arxiv_id=arxiv_id,
            year=update.year,
            venue=update.venue,
            metadata_status=MetadataStatus.USER_PROVIDED,
            metadata_sources=sources,
        )
        self._papers.commit()
        refreshed = self.get_entry(user_id=user_id, user_paper_id=user_paper_id)
        assert refreshed is not None
        logger.info(
            "service.library.info_edited",
            user_paper_id=str(user_paper_id),
            fields=[entry_["field"] for entry_ in sources],
        )
        return refreshed

    def fetch_metadata(
        self,
        *,
        user_id: UUID,
        user_paper_id: UUID,
        identifier: Identifier | None = None,
    ) -> MetadataFetchResult:
        """按标识符在线获取元数据；失败只记录原因，不改动已有内容。"""
        entry = self._require_entry(user_id=user_id, user_paper_id=user_paper_id)
        identifier = identifier or _identifier_of(entry.user_paper)
        if identifier is None:
            return MetadataFetchResult(
                entry=entry,
                status=entry.user_paper.metadata_status,
                error_code=str(ErrorCode.IDENTIFIER_INVALID),
            )

        outcome = self._resolver.resolve(identifier)
        if outcome.metadata is None:
            self._papers.commit()
            logger.info(
                "service.library.metadata_incomplete",
                user_paper_id=str(user_paper_id),
                status=outcome.status.value,
                error_code=str(outcome.error_code) if outcome.error_code else None,
            )
            return MetadataFetchResult(
                entry=entry,
                status=outcome.status,
                source=outcome.source,
                error_code=str(outcome.error_code) if outcome.error_code else None,
            )

        applied = self._apply_entry_metadata(
            entry.user_paper,
            outcome.metadata,
            identifier,
        )
        if entry.paper is not None:
            self._apply_paper_metadata(entry.paper, outcome.metadata)
        self._papers.commit()
        refreshed = self.get_entry(user_id=user_id, user_paper_id=user_paper_id)
        assert refreshed is not None
        logger.info(
            "service.library.metadata_fetched",
            user_paper_id=str(user_paper_id),
            source=outcome.source,
            status=outcome.status.value,
        )
        return MetadataFetchResult(
            entry=refreshed,
            status=outcome.status,
            source=outcome.source,
            applied_fields=tuple(sorted(applied)),
            provider_metadata=outcome.metadata,
        )

    # Queries ---------------------------------------------------------------
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
        if paper is None or not paper.has_fulltext:
            return None
        version = paper.artifact_manifest_key or paper.updated_at.isoformat()
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

    def _finish_write(
        self,
        user_id: UUID,
        user_paper: UserPaper,
        paper: Paper,
    ) -> tuple[LibraryEntry, IngestionJob | None]:
        # The entry becomes durable before any processing starts, so the user
        # can always see it and the job runner always finds its paper.
        self._papers.commit()
        job = self._ingestion.start_for_paper(paper.id)
        # The job may already have finished (inline runner) or be running in
        # another session, so drop this session's cached rows before re-reading.
        self._papers.expire_all()
        entry = self.get_entry(user_id=user_id, user_paper_id=user_paper.id)
        assert entry is not None
        return entry, job

    def _ensure_no_identifier_conflict(
        self,
        user_paper: UserPaper,
        stored: StoredPdf,
    ) -> None:
        """A different identifier in the file must not silently replace data."""
        for identifier in stored.detected_identifiers:
            if identifier.type is IdentifierType.DOI:
                existing = user_paper.doi
            else:
                existing = user_paper.arxiv_id
            if existing and existing.lower() != identifier.value.lower():
                raise ConflictError(
                    "该 PDF 识别出的标识符与条目已有标识符冲突，请确认后再处理",
                    code=ErrorCode.METADATA_CONFLICT,
                    details={
                        "existing": existing,
                        "detected": identifier.value,
                        "type": identifier.type.value,
                    },
                )

    def _apply_entry_metadata(
        self,
        user_paper: UserPaper,
        metadata: ProviderMetadata,
        identifier: Identifier,
    ) -> set[str]:
        """Apply provider fields, never overwriting user corrections.

        An exact identifier lookup is authoritative for its own paper, so a
        provider value replaces a placeholder (for example a filename-derived
        title) unless the user corrected that field.
        """
        merged = merge_provider_metadata(user_paper, metadata)
        applied = set(merged.applied_fields)
        doi = merged.doi
        arxiv_id = merged.arxiv_id
        if doi is None and identifier.type is IdentifierType.DOI:
            doi = identifier.value
            applied.add("doi")
        if arxiv_id is None and identifier.type is IdentifierType.ARXIV:
            arxiv_id = identifier.value
            applied.add("arxiv_id")

        self._papers.update_user_paper_metadata(
            user_paper.id,
            title=merged.title,
            authors=merged.authors or None,
            abstract=merged.abstract,
            doi=doi,
            arxiv_id=arxiv_id,
            year=merged.year,
            venue=merged.venue,
            bibliographic={
                **(user_paper.bibliographic or {}),
                "provider": metadata.bibliographic(),
            },
            metadata_status=metadata.metadata_status(),
            metadata_sources=merge_sources(
                user_paper.metadata_sources,
                sorted(applied),
                source=metadata.source,
            ),
        )
        return applied

    def _apply_paper_metadata(self, paper: Paper, metadata: ProviderMetadata) -> None:
        """Merge provider fields into the shared paper facts (fill-only)."""
        current = paper.bibliographic or {}
        merged = dict(current)
        for key, value in metadata.bibliographic().items():
            if value and not merged.get(key):
                merged[key] = value
        self._papers.set_paper_metadata(
            paper.id,
            bibliographic=merged,
            metadata_status=metadata.metadata_status(),
            metadata_sources=paper.metadata_sources,
        )

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


def _identifier_of(user_paper: UserPaper) -> Identifier | None:
    if user_paper.doi:
        try:
            return parse_identifier(user_paper.doi)
        except AppError:
            pass
    if user_paper.arxiv_id:
        try:
            return parse_identifier(user_paper.arxiv_id)
        except AppError:
            pass
    return None


def _normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    identifier = parse_identifier(normalized)
    if identifier.type is not IdentifierType.DOI:
        raise AppError(
            "该字段需要 DOI 形式的标识符",
            code=ErrorCode.IDENTIFIER_INVALID,
            status_code=422,
        )
    return identifier.value


def _normalize_arxiv(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    identifier = parse_identifier(normalized)
    if identifier.type is not IdentifierType.ARXIV:
        raise AppError(
            "该字段需要 arXiv 形式的标识符",
            code=ErrorCode.IDENTIFIER_INVALID,
            status_code=422,
        )
    return identifier.value


def _truncate(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:MAX_FILENAME_LENGTH]
