"""Sequential execution of the ingestion stages for one job.

Stage order is metadata → fulltext → chunking → embedding. Stage outputs are
persisted as they are produced, so a later failure never hides an earlier
capability. Only blocking stages stop the job; metadata is best effort.
"""

import asyncio
import hashlib
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from app.library.domain import MetadataStatus
from app.library.repo import PaperRepository
from app.literature_support.embedding import build_embedding_adapter
from app.literature_support.processing.blocks import build_block_index
from app.literature_support.processing.chunks import build_chunks
from app.literature_support.processing.mineru import MineruParser
from app.literature_support.processing.text import detect_identifiers
from app.literature_support.scholar.identifiers import Identifier, IdentifierType
from app.literature_support.scholar.merge import merge_provider_metadata, merge_sources
from app.literature_support.scholar.metadata import (
    MetadataResolver,
    build_default_resolver,
)
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
from app.processing.domain import STAGE_ORDER, IngestionJob, IngestionStage, StageStatus
from app.processing.repo import IngestionRepository
from app.processing.service import IngestionService
from app.retrieval.ports import EmbeddingAdapter
from app.retrieval.repo import ChunkRepository

logger = structlog.get_logger(__name__)

EMBEDDING_BATCH_SIZE = 32
NON_BLOCKING_STAGES = {IngestionStage.METADATA}
CONTENT_LIST_OBJECT = "content_list.json"
BLOCKS_INDEX_OBJECT = "blocks_index.json"
MARKDOWN_OBJECT = "full.md"


class IngestionPipeline:
    """Runs one job's stages; safe to call more than once per job."""

    def __init__(
        self,
        *,
        scheduler: TaskScheduler | None,
        session_factory: SessionFactory,
        storage: ObjectStorage,
        mineru: MineruParser,
        resolver: MetadataResolver,
        embeddings: EmbeddingAdapter,
        target_tokens: int | None = None,
        max_chars: int | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._storage = storage
        self._mineru = mineru
        self._resolver = resolver
        self._embeddings = embeddings
        self._target_tokens = target_tokens or settings.chunk_token_num
        self._max_chars = max_chars or settings.chunk_max_chars

    def submit(self, job_id: UUID) -> None:
        if self._scheduler is None:
            return
        self._scheduler.submit(
            lambda: self._run(job_id),
            name=f"ingestion:{job_id}",
        )

    async def _run(self, job_id: UUID) -> None:
        # Database access is synchronous, so the work runs in a worker thread
        # and never blocks the event loop.
        await asyncio.to_thread(self.run_sync, job_id)

    def run_sync(self, job_id: UUID) -> None:
        session = self._session_factory()
        try:
            repository = IngestionRepository(session)
            papers = PaperRepository(session)
            chunks = ChunkRepository(session)

            job = repository.get_job(job_id)
            if job is None:
                return
            paper = papers.get_paper(job.paper_id)
            if paper is None:
                repository.finish_job(job_id, error_code=str(ErrorCode.PAPER_NOT_FOUND))
                session.commit()
                return

            blocking_failure: str | None = None
            for stage in STAGE_ORDER:
                stage_state = job.stage(stage)
                if stage_state is None or stage_state.status is not StageStatus.PENDING:
                    continue
                repository.mark_running(job_id, stage=stage)
                session.commit()
                try:
                    progress = self._run_stage(
                        stage,
                        repository=repository,
                        papers=papers,
                        chunks=chunks,
                        job=job,
                    )
                except AppError as exc:
                    repository.mark_stage_failed(
                        job_id,
                        stage=stage,
                        error_code=str(exc.code),
                        error_message=exc.message,
                    )
                    session.commit()
                    logger.info(
                        "pipeline.stage_failed",
                        job_id=str(job_id),
                        stage=stage.value,
                        error_code=str(exc.code),
                    )
                    if stage not in NON_BLOCKING_STAGES:
                        blocking_failure = str(exc.code)
                        break
                except Exception as exc:  # unexpected: stop and record it
                    repository.mark_stage_failed(
                        job_id,
                        stage=stage,
                        error_code=str(ErrorCode.INTERNAL_ERROR),
                        error_message=type(exc).__name__,
                    )
                    session.commit()
                    logger.exception(
                        "pipeline.stage_crashed",
                        job_id=str(job_id),
                        stage=stage.value,
                        error_type=type(exc).__name__,
                    )
                    blocking_failure = str(ErrorCode.INTERNAL_ERROR)
                    break
                else:
                    repository.mark_stage_succeeded(
                        job_id,
                        stage=stage,
                        progress=progress,
                    )
                    session.commit()

            repository.finish_job(job_id, error_code=blocking_failure)
            session.commit()
            logger.info(
                "pipeline.finished",
                job_id=str(job_id),
                status="failed" if blocking_failure else "succeeded",
                error_code=blocking_failure,
            )
        finally:
            session.close()

    # Stages ----------------------------------------------------------------
    def _run_stage(
        self,
        stage: IngestionStage,
        *,
        repository: IngestionRepository,
        papers: PaperRepository,
        chunks: ChunkRepository,
        job: IngestionJob,
    ) -> dict | None:
        paper = papers.get_paper(job.paper_id)
        if paper is None:
            raise AppError(
                "论文不存在", code=ErrorCode.PAPER_NOT_FOUND, status_code=404
            )
        if stage is IngestionStage.METADATA:
            return self._metadata_stage(papers, paper)
        if stage is IngestionStage.FULLTEXT:
            return self._fulltext_stage(papers, paper.id, paper.file_hash, job.id)
        if stage is IngestionStage.CHUNKING:
            return self._chunking_stage(papers, chunks, paper)
        return self._embedding_stage(papers, chunks, paper.id)

    def _metadata_stage(self, papers: PaperRepository, paper) -> dict:
        """Lightweight local recognition followed by an exact online lookup."""
        with self._pdf_file(paper.file_hash) as pdf_path:
            identifiers = detect_identifiers(pdf_path)
        if not identifiers:
            papers.set_paper_metadata(
                paper.id,
                bibliographic=paper.bibliographic,
                metadata_status=MetadataStatus.UNRECOGNIZED,
                metadata_sources=paper.metadata_sources,
            )
            return {"outcome": MetadataStatus.UNRECOGNIZED.value, "identifiers": 0}

        identifier = _preferred_identifier(identifiers)
        outcome = self._resolver.resolve(identifier)
        if outcome.metadata is None:
            papers.set_paper_metadata(
                paper.id,
                bibliographic=paper.bibliographic,
                metadata_status=outcome.status,
                metadata_sources=[_source_entry(identifier, outcome.source)],
            )
            progress = {
                "outcome": outcome.status.value,
                "identifier_type": identifier.type.value,
                "identifier": identifier.value,
            }
            if outcome.status is MetadataStatus.PROVIDER_FAILED:
                # Metadata is best effort: record the failure but keep parsing
                # the body, which does not depend on bibliographic data.
                raise AppError(
                    "元数据在线补全失败，正文处理继续",
                    code=outcome.error_code or ErrorCode.METADATA_PROVIDER_FAILED,
                    status_code=502,
                )
            return progress

        papers.set_paper_metadata(
            paper.id,
            bibliographic=outcome.metadata.bibliographic(),
            metadata_status=outcome.status,
            metadata_sources=[_source_entry(identifier, outcome.source)],
        )
        self._propagate_metadata(papers, paper.id, outcome.metadata, identifier)
        return {
            "outcome": outcome.status.value,
            "source": outcome.source,
            "identifier_type": identifier.type.value,
        }

    def _propagate_metadata(
        self,
        papers: PaperRepository,
        paper_id: UUID,
        metadata,
        identifier: Identifier,
    ) -> None:
        """Let recognized metadata replace filename placeholders on entries.

        Each entry keeps its own user corrections; async recognition never
        overwrites a field the user edited.
        """
        for entry in papers.entries_for_paper(paper_id):
            merged = merge_provider_metadata(entry, metadata)
            doi = merged.doi
            arxiv_id = merged.arxiv_id
            if doi is None and identifier.type is IdentifierType.DOI:
                doi = identifier.value
            if arxiv_id is None and identifier.type is IdentifierType.ARXIV:
                arxiv_id = identifier.value
            papers.update_user_paper_metadata(
                entry.id,
                title=merged.title,
                authors=merged.authors or None,
                abstract=merged.abstract,
                doi=doi,
                arxiv_id=arxiv_id,
                year=merged.year,
                venue=merged.venue,
                metadata_status=metadata.metadata_status(),
                metadata_sources=merge_sources(
                    entry.metadata_sources,
                    list(merged.applied_fields),
                    source=metadata.source,
                ),
            )

    def _fulltext_stage(
        self,
        papers: PaperRepository,
        paper_id: UUID,
        file_hash: str,
        job_id: UUID,
    ) -> dict:
        artifact_prefix = mineru_job_artifact_key(file_hash, str(job_id), "")
        self._storage.delete_prefix(artifact_prefix)
        with self._pdf_file(file_hash) as pdf_path:
            artifact = self._mineru.parse(pdf_path=pdf_path)
        files: dict[str, dict] = {}

        def write(relative_path: str, payload: bytes) -> None:
            key = mineru_job_artifact_key(file_hash, str(job_id), relative_path)
            self._storage.put_bytes(key, payload)
            files[relative_path] = {
                "key": key,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }

        manifest_key = mineru_job_artifact_key(file_hash, str(job_id), "manifest.json")
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
                "job_id": str(job_id),
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
                    job_id=str(job_id),
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
                    code=ErrorCode.INGESTION_ARTIFACT_INVALID,
                    status_code=502,
                )
            entry = manifest["files"][CONTENT_LIST_OBJECT]
            raw = self._storage.read_bytes(entry["key"])
            if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise AppError(
                    "MinerU 产物校验失败",
                    code=ErrorCode.INGESTION_ARTIFACT_INVALID,
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
                code=ErrorCode.INGESTION_ARTIFACT_INVALID,
                status_code=502,
            )
        for draft in drafts:
            assert draft.chunk_metadata is not None
            draft.chunk_metadata["artifact_manifest_key"] = paper.artifact_manifest_key
        count = chunks.replace_chunks(paper_id=paper.id, drafts=drafts)
        papers.set_paper_capabilities(paper.id, has_keyword_index=True)
        return {"chunks": count}

    def _embedding_stage(
        self,
        papers: PaperRepository,
        chunks: ChunkRepository,
        paper_id: UUID,
    ) -> dict:
        if not self._embeddings.is_configured:
            raise AppError(
                "Embedding 服务未配置",
                code=ErrorCode.PROVIDER_NOT_CONFIGURED,
                status_code=503,
            )
        indexed = 0
        for batch in _batched(
            chunks.pending_embedding_chunks(paper_id), EMBEDDING_BATCH_SIZE
        ):
            # 前缀与截断由适配器按模型档案处理，这里只负责分批
            vectors = self._embeddings.embed_documents(
                [chunk.content for chunk in batch],
            )
            for chunk, vector in zip(batch, vectors, strict=True):
                chunks.set_embedding(
                    chunk_id=chunk.id,
                    embedding=vector,
                    model=self._embeddings.model,
                )
            indexed += len(batch)
        papers.set_paper_capabilities(paper_id, has_embedding=True)
        return {"embedded": indexed, "model": self._embeddings.model}

    @contextmanager
    def _pdf_file(self, file_hash: str) -> Iterator[Path]:
        """PDF 在本地实现下是零拷贝；S3 实现会下载到临时文件。"""
        with self._storage.materialize(paper_pdf_key(file_hash)) as path:
            yield path


def _preferred_identifier(identifiers: Sequence[Identifier]) -> Identifier:
    for identifier in identifiers:
        if identifier.type is IdentifierType.DOI:
            return identifier
    return identifiers[0]


def _source_entry(identifier: Identifier, source: str | None) -> dict:
    return {
        "field": identifier.type.value,
        "value": identifier.value,
        "source": source or "local_recognition",
        "at": datetime.now(UTC).isoformat(),
    }


def _batched(items: list, size: int) -> list[list]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def build_ingestion_service(
    *,
    session: Session,
    storage: ObjectStorage,
    session_factory: SessionFactory,
    scheduler: TaskScheduler,
) -> IngestionService:
    """Assemble ingestion services for HTTP requests, imports and agent tools."""
    papers = PaperRepository(session)
    pipeline = IngestionPipeline(
        scheduler=scheduler,
        session_factory=session_factory,
        storage=storage,
        mineru=MineruParser(
            base_url=settings.mineru_api_url,
            api_key=settings.mineru_api_key,
            timeout_seconds=settings.mineru_timeout_seconds,
        ),
        resolver=build_default_resolver(),
        embeddings=build_embedding_adapter(),
        target_tokens=settings.chunk_token_num,
        max_chars=settings.chunk_max_chars,
    )
    return IngestionService(IngestionRepository(session), papers, runner=pipeline)
