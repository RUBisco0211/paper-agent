"""Sequential execution of the ingestion stages for one job.

Stage order is metadata → fulltext → chunking → embedding. Stage outputs are
persisted as they are produced, so a later failure never hides an earlier
capability. Only blocking stages stop the job; metadata is best effort.
"""

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog

from ..library.domain import MetadataStatus
from ..library.metadata_merge import merge_provider_metadata, merge_sources
from ..library.persistence import PaperRepository
from ..library.text_extraction import detect_identifiers
from ..platform.config import settings
from ..platform.database import SessionFactory
from ..platform.errors import AppError, ErrorCode
from ..platform.storage import (
    ObjectStorage,
    mineru_artifact_key,
    paper_pdf_key,
)
from ..platform.tasks import TaskScheduler
from ..retrieval.embedding import EmbeddingAdapter
from ..retrieval.persistence import ChunkRepository
from ..scholar.identifiers import Identifier, IdentifierType
from ..scholar.metadata import MetadataResolver
from .chunking import build_chunks
from .domain import STAGE_ORDER, IngestionJob, IngestionStage, StageStatus
from .mineru import MineruParser
from .persistence import IngestionRepository

logger = structlog.get_logger(__name__)

EMBEDDING_BATCH_SIZE = 32
NON_BLOCKING_STAGES = {IngestionStage.METADATA}
CONTENT_LIST_OBJECT = "content_list.json"
MARKDOWN_OBJECT = "full.md"


class IngestionPipeline:
    """Runs one job's stages; safe to call more than once per job."""

    def __init__(
        self,
        *,
        scheduler: TaskScheduler,
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
            return self._fulltext_stage(papers, paper.id, paper.file_hash)
        if stage is IngestionStage.CHUNKING:
            return self._chunking_stage(papers, chunks, paper.id, paper.file_hash)
        return self._embedding_stage(papers, chunks, paper.id)

    def _metadata_stage(self, papers: PaperRepository, paper) -> dict:
        """Lightweight local recognition followed by an exact online lookup."""
        identifiers = detect_identifiers(self._pdf_path(paper.file_hash))
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
    ) -> dict:
        artifact = self._mineru.parse(pdf_path=self._pdf_path(file_hash))
        self._storage.put_bytes(
            mineru_artifact_key(file_hash, CONTENT_LIST_OBJECT),
            json.dumps(artifact.content_list, ensure_ascii=False).encode("utf-8"),
        )
        if artifact.markdown:
            self._storage.put_bytes(
                mineru_artifact_key(file_hash, MARKDOWN_OBJECT),
                artifact.markdown.encode("utf-8"),
            )
        for name, payload in artifact.images.items():
            self._storage.put_bytes(
                mineru_artifact_key(file_hash, f"images/{name}"),
                payload,
            )
        papers.set_paper_capabilities(paper_id, has_fulltext=True)
        papers.set_parser_version(paper_id, artifact.version)
        return {
            "blocks": len(artifact.content_list),
            "images": len(artifact.images),
            "parser_version": artifact.version,
        }

    def _chunking_stage(
        self,
        papers: PaperRepository,
        chunks: ChunkRepository,
        paper_id: UUID,
        file_hash: str,
    ) -> dict:
        payload = json.loads(
            self._storage.read_text(
                mineru_artifact_key(file_hash, CONTENT_LIST_OBJECT)
            ),
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
        count = chunks.replace_chunks(paper_id=paper_id, drafts=drafts)
        papers.set_paper_capabilities(paper_id, has_keyword_index=True)
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

    def _pdf_path(self, file_hash: str) -> Path:
        return self._storage.local_path(paper_pdf_key(file_hash))


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
