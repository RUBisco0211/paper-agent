"""Run one import's stages in order: source → parse → chunk → embed.

Each stage writes its own artifact before the next begins, so a later failure
never hides an earlier result and a retry skips what already succeeded.
Bibliographic lookup is not a stage: it runs beside this flow.
"""

import asyncio
import hashlib
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from app.library.domain import PaperSource
from app.library.repo import PaperRepository
from app.literature_support.embedding import build_embedding_adapter
from app.literature_support.importing.blocks import build_block_index
from app.literature_support.importing.chunks import build_chunks
from app.literature_support.importing.mineru import MineruParser
from app.platform.config import settings
from app.platform.database import SessionFactory
from app.platform.errors import AppError, ErrorCode
from app.platform.storage import (
    ObjectStorage,
    mineru_artifact_key,
    mineru_job_artifact_key,
    paper_pdf_key,
)
from app.platform.tasks import TaskScheduler
from app.imports.domain import (
    STAGE_ORDER,
    ImportStage,
    ImportStatus,
    PaperImport,
    StageStatus,
    source_of,
)
from app.imports.ports import SourceAcquirer
from app.imports.queue import ImportQueueService
from app.imports.repo import ImportRepository
from app.retrieval.ports import EmbeddingAdapter
from app.retrieval.repo import ChunkRepository

logger = structlog.get_logger(__name__)

CONTENT_LIST_OBJECT = "content_list.json"
BLOCKS_INDEX_OBJECT = "blocks_index.json"
MARKDOWN_OBJECT = "full.md"


class ImportPipeline:
    """Runs one import's stages; safe to call more than once per import."""

    def __init__(
        self,
        *,
        scheduler: TaskScheduler | None,
        session_factory: SessionFactory,
        storage: ObjectStorage,
        mineru: MineruParser,
        embeddings: EmbeddingAdapter,
        acquirer: SourceAcquirer | None = None,
        target_tokens: int | None = None,
        max_chars: int | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._storage = storage
        self._mineru = mineru
        self._embeddings = embeddings
        self._acquirer = acquirer
        self._target_tokens = target_tokens or settings.chunk_token_num
        self._max_chars = max_chars or settings.chunk_max_chars

    def submit(self, import_id: UUID) -> None:
        self._schedule(import_id)

    def submit_stages(self, import_id: UUID) -> None:
        """Run whatever stages are still pending; the source file is in place."""
        self._schedule(import_id)

    def _schedule(self, import_id: UUID) -> None:
        if self._scheduler is None:
            return
        self._scheduler.submit(
            lambda: self._run(import_id),
            name=f"import:{import_id}",
        )

    async def _run(self, import_id: UUID) -> None:
        # Database access is synchronous, so the work runs in a worker thread
        # and never blocks the event loop.
        await asyncio.to_thread(self.run_sync, import_id)

    def run_sync(self, import_id: UUID) -> None:
        session = self._session_factory()
        try:
            repository = ImportRepository(session)
            papers = PaperRepository(session)
            chunks = ChunkRepository(session)

            record = repository.get(import_id)
            if record is None:
                return

            failure: str | None = None
            for stage in STAGE_ORDER:
                state = record.stage(stage)
                if state is None or state.status is not StageStatus.PENDING:
                    continue

                repository.mark_stage_running(import_id, stage=stage)
                session.commit()
                try:
                    progress = self._run_stage(
                        stage,
                        repository=repository,
                        papers=papers,
                        chunks=chunks,
                        record=record,
                    )
                except AppError as exc:
                    repository.mark_stage_failed(
                        import_id,
                        stage=stage,
                        error_code=str(exc.code),
                        error_message=exc.message,
                    )
                    session.commit()
                    logger.info(
                        "import.stage_failed",
                        import_id=str(import_id),
                        stage=stage.value,
                        error_code=str(exc.code),
                        detail=_safe_error_details(exc.details),
                    )
                    failure = str(exc.code)
                    break
                except Exception as exc:  # unexpected: stop and record it
                    repository.mark_stage_failed(
                        import_id,
                        stage=stage,
                        error_code=str(ErrorCode.INTERNAL_ERROR),
                        error_message=type(exc).__name__,
                    )
                    session.commit()
                    logger.exception(
                        "import.stage_crashed",
                        import_id=str(import_id),
                        stage=stage.value,
                        error_type=type(exc).__name__,
                    )
                    failure = str(ErrorCode.INTERNAL_ERROR)
                    break
                else:
                    repository.mark_stage_succeeded(
                        import_id, stage=stage, progress=progress
                    )
                    session.commit()
                    # The source stage may have created the paper.
                    record = repository.get(import_id) or record

            if failure is None:
                # A stage left pending or failed must never pass as ready.
                unfinished = [
                    stage.value
                    for stage in (
                        (repository.get(import_id) or record).stages
                    )
                    if stage.status is not StageStatus.SUCCEEDED
                ]
                if unfinished:
                    raise RuntimeError(
                        f"import {import_id} reached the end with unfinished "
                        f"stages: {unfinished}"
                    )
                repository.finish(import_id, status=ImportStatus.READY)
                session.commit()
                # Every stage finished: the entry may now appear in the library.
                self._reveal_entry(papers, record, session)
            else:
                # No source file is its own outcome: nothing else can run, but
                # it is not an internal failure.
                terminal = (
                    ImportStatus.SOURCE_UNAVAILABLE
                    if failure == str(ErrorCode.PAPER_PDF_NOT_AVAILABLE)
                    else ImportStatus.FAILED
                )
                repository.finish(import_id, status=terminal, error_code=failure)
                session.commit()
            logger.info(
                "import.finished",
                import_id=str(import_id),
                status="failed" if failure else "ready",
                error_code=failure,
            )
        finally:
            session.close()

    def _reveal_entry(
        self,
        papers: PaperRepository,
        record: PaperImport,
        session: Session,
    ) -> None:
        """Make the requester's entry visible now that the paper is usable."""
        if record.paper_id is None:
            return
        papers.link_paper(
            user_id=record.initiated_by,
            paper_id=record.paper_id,
            source=source_of(record.identifier_type),
        )
        # Everyone waiting on this paper sees it at once.
        papers.mark_entries_ready(paper_id=record.paper_id)
        session.commit()
        logger.info(
            "import.linked",
            import_id=str(record.id),
            user_id=str(record.initiated_by),
        )


    # Stages ----------------------------------------------------------------
    def _run_stage(
        self,
        stage: ImportStage,
        *,
        repository: ImportRepository,
        papers: PaperRepository,
        chunks: ChunkRepository,
        record: PaperImport,
    ) -> dict | None:
        if stage is ImportStage.SOURCE:
            return self._source_stage(repository, record)

        paper = papers.get_paper(record.paper_id)
        if paper is None:
            raise AppError(
                "论文不存在", code=ErrorCode.PAPER_NOT_FOUND, status_code=404
            )
        if stage is ImportStage.PARSE:
            return self._parse_stage(papers, paper.id, paper.file_hash, record.id)
        if stage is ImportStage.CHUNK:
            return self._chunking_stage(papers, chunks, paper)
        return self._embedding_stage(papers, chunks, paper.id)

    def _source_stage(
        self,
        repository: ImportRepository,
        record: PaperImport,
    ) -> dict:
        """Obtain the file whose absence would make the paper impossible.

        Uploads arrive with the paper already bound; an identifier import has to
        fetch it, and the whole import fails when no source can be found.
        """
        if record.paper_id is not None:
            return {"stored": True}
        if self._acquirer is None:
            raise AppError(
                "没有可用的原文来源",
                code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                status_code=422,
            )
        paper_id = self._acquirer.acquire(record.id)
        if paper_id is None:
            raise AppError(
                "没有可用的原文来源",
                code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                status_code=422,
            )
        return {"stored": True, "paper_id": str(paper_id)}

    def _parse_stage(
        self,
        papers: PaperRepository,
        paper_id: UUID,
        file_hash: str,
        import_id: UUID,
    ) -> dict:
        artifact_prefix = mineru_job_artifact_key(file_hash, str(import_id), "")
        self._storage.delete_prefix(artifact_prefix)
        with self._pdf_file(file_hash) as pdf_path:
            artifact = self._mineru.parse(pdf_path=pdf_path)
        files: dict[str, dict] = {}

        def write(relative_path: str, payload: bytes) -> None:
            key = mineru_job_artifact_key(file_hash, str(import_id), relative_path)
            self._storage.put_bytes(key, payload)
            files[relative_path] = {
                "key": key,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }

        manifest_key = mineru_job_artifact_key(
            file_hash, str(import_id), "manifest.json"
        )
        try:
            write(
                CONTENT_LIST_OBJECT,
                json.dumps(artifact.content_list, ensure_ascii=False).encode("utf-8"),
            )
            write(
                BLOCKS_INDEX_OBJECT,
                json.dumps(
                    build_block_index(artifact.content_list), ensure_ascii=False
                ).encode("utf-8"),
            )
            if artifact.markdown:
                write(MARKDOWN_OBJECT, artifact.markdown.encode("utf-8"))
            for name, payload in artifact.images.items():
                write(name if name.startswith("images/") else f"images/{name}", payload)
            manifest = {
                "schema_version": 1,
                "job_id": str(import_id),
                "file_hash": file_hash,
                "parser_version": artifact.version,
                "files": files,
            }
            self._storage.put_bytes(
                manifest_key,
                json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode(
                    "utf-8"
                ),
            )
        except Exception:
            try:
                self._storage.delete_prefix(artifact_prefix)
            except Exception as cleanup_error:
                logger.warning(
                    "pipeline.artifact_cleanup_failed",
                    import_id=str(import_id),
                    error_type=type(cleanup_error).__name__,
                )
            raise
        papers.publish_artifact(
            paper_id, manifest_key=manifest_key, parser_version=artifact.version
        )
        return {
            "blocks": len(artifact.content_list),
            "images": len(artifact.images),
            "parser_version": artifact.version,
        }

    def _chunking_stage(
        self,
        papers: PaperRepository,
        chunks: ChunkRepository,
        paper,
    ) -> dict:
        if paper.artifact_manifest_key:
            manifest = json.loads(self._storage.read_text(paper.artifact_manifest_key))
            if manifest.get("file_hash") != paper.file_hash:
                raise AppError(
                    "MinerU 产物与论文不匹配",
                    code=ErrorCode.IMPORT_ARTIFACT_INVALID,
                    status_code=502,
                )
            entry = manifest["files"][CONTENT_LIST_OBJECT]
            raw = self._storage.read_bytes(entry["key"])
            if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise AppError(
                    "MinerU 产物校验失败",
                    code=ErrorCode.IMPORT_ARTIFACT_INVALID,
                    status_code=502,
                )
            payload = json.loads(raw)
        else:
            payload = json.loads(
                self._storage.read_text(
                    mineru_artifact_key(paper.file_hash, CONTENT_LIST_OBJECT)
                )
            )
        drafts = build_chunks(
            payload,
            target_tokens=self._target_tokens,
            max_chars=self._max_chars,
        )
        if not drafts:
            raise AppError(
                "MinerU 产物中没有可索引的内容",
                code=ErrorCode.IMPORT_ARTIFACT_INVALID,
                status_code=502,
            )
        for draft in drafts:
            assert draft.chunk_metadata is not None
            draft.chunk_metadata["artifact_manifest_key"] = paper.artifact_manifest_key
        count = chunks.replace_chunks(paper_id=paper.id, drafts=drafts)
        return {"chunks": count}

    def _embedding_stage(
        self,
        papers: PaperRepository,
        chunks: ChunkRepository,
        paper_id: UUID,
    ) -> dict:
        embeddings = self._embeddings
        if not embeddings.is_configured:
            raise AppError(
                "Embedding 服务未配置",
                code=ErrorCode.PROVIDER_NOT_CONFIGURED,
                status_code=503,
            )
        # 整篇一次交给适配器：切分只在适配器发生，按模型档案的条数与字符上限，
        # 不再在流水线里预先切成固定大小（旧做法会在尾批里塞进不完整的一批）。
        pending = chunks.pending_embedding_chunks(paper_id)
        if pending:
            vectors = embeddings.embed_documents([chunk.content for chunk in pending])
            for chunk, vector in zip(pending, vectors, strict=True):
                chunks.set_embedding(
                    chunk_id=chunk.id,
                    embedding=vector,
                    model=embeddings.model,
                )
        return {"embedded": len(pending), "model": embeddings.model}

    @contextmanager
    def _pdf_file(self, file_hash: str) -> Iterator[Path]:
        """PDF 在本地实现下是零拷贝；S3 实现会下载到临时文件。"""
        with self._storage.materialize(paper_pdf_key(file_hash)) as path:
            yield path


def _safe_error_details(details: object) -> dict[str, int]:
    """Only adapter diagnostics with known numeric meanings may enter logs."""
    if not isinstance(details, dict):
        return {}
    allowed = {
        "status", "expected", "returned", "expected_dimensions", "actual_dimensions",
    }
    return {key: value for key, value in details.items()
            if key in allowed and type(value) is int}


def build_import_pipeline(
    *,
    storage: ObjectStorage,
    session_factory: SessionFactory,
    scheduler: TaskScheduler,
    acquirer: SourceAcquirer | None = None,
) -> ImportPipeline:
    """The stage pipeline on its own, for callers that drive a specific import."""
    return ImportPipeline(
        scheduler=scheduler,
        session_factory=session_factory,
        storage=storage,
        acquirer=acquirer,
        mineru=MineruParser(
            base_url=settings.mineru_api_url,
            api_key=settings.mineru_api_key,
            timeout_seconds=settings.mineru_timeout_seconds,
        ),
        embeddings=build_embedding_adapter(),
        target_tokens=settings.chunk_token_num,
        max_chars=settings.chunk_max_chars,
    )


def build_import_service(
    *,
    session: Session,
    storage: ObjectStorage,
    session_factory: SessionFactory,
    scheduler: TaskScheduler,
) -> ImportQueueService:
    """Assemble the import workflow for HTTP requests, imports and agent tools."""
    papers = PaperRepository(session)
    pipeline = build_import_pipeline(
        storage=storage,
        session_factory=session_factory,
        scheduler=scheduler,
    )
    return ImportQueueService(
        ImportRepository(session),
        papers,
        runner=pipeline,
    )


def build_source_acquirer(
    *,
    session_factory: SessionFactory,
    storage: ObjectStorage,
    scheduler: TaskScheduler,
):
    """The downloader the worker uses for identifier imports."""
    from app.imports.service import ImportService
    from app.literature_support.scholar.metadata import build_default_resolver
    from app.literature_support.scholar.pdf_fetch import PdfFetcher
    from app.literature_support.scholar.pdf_sources import DoiPdfLocator

    return ImportService(
        session_factory=session_factory,
        storage=storage,
        resolver=build_default_resolver(),
        pdf_fetcher=PdfFetcher(max_bytes=settings.max_pdf_bytes),
        pdf_locator=DoiPdfLocator(),
        scheduler=scheduler,
        import_starter_factory=build_import_service,
    )
