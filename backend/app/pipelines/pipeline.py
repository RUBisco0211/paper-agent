"""Run a paper's stages in order: parse → chunk → embed.

Every stage decides for itself whether it still has work, by looking at the
artifacts rather than at a flag, so a run interrupted anywhere resumes cheaply
and a half-written artifact is repaired instead of trusted.
"""

import asyncio
import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.library.repo import PaperRepository
from app.literature_support.embedding import build_embedding_adapter
from app.literature_support.importing.blocks import build_block_index
from app.literature_support.importing.chunks import build_chunks
from app.literature_support.importing.mineru import MineruParser
from app.platform.config import settings
from app.platform.database import SessionFactory
from app.platform.errors import AppError, ErrorCode
from app.platform.storage import ObjectStorage, mineru_artifact_key, paper_pdf_key
from app.platform.tasks import TaskScheduler
from app.projects.repo import ProjectRepository
from app.retrieval.ports import EmbeddingAdapter
from app.retrieval.repo import ChunkRepository

from ..pipelines.domain import RunStage, next_stage
from ..pipelines.repo import RunRepository

logger = structlog.get_logger(__name__)

CONTENT_LIST_OBJECT = "content_list.json"
BLOCKS_INDEX_OBJECT = "blocks_index.json"
MARKDOWN_OBJECT = "full.md"
MANIFEST_OBJECT = "manifest.json"

#: How long one worker owns a claimed run before another may declare it dead.
LEASE_SECONDS = 300


class RunPipeline:
    """Runs a paper's stages; safe to call more than once for the same run."""

    def __init__(
        self,
        *,
        scheduler: TaskScheduler | None,
        session_factory: SessionFactory,
        storage: ObjectStorage,
        mineru: MineruParser,
        embeddings: EmbeddingAdapter,
        target_tokens: int | None = None,
        max_chars: int | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._storage = storage
        self._mineru = mineru
        self._embeddings = embeddings
        self._target_tokens = target_tokens or settings.chunk_token_num
        self._max_chars = max_chars or settings.chunk_max_chars

    def submit(self, run_id: UUID) -> None:
        self._schedule(run_id)

    def _schedule(self, run_id: UUID) -> None:
        if self._scheduler is None:
            return
        self._scheduler.submit(lambda: self._run(run_id), name=f"run:{run_id}")

    async def _run(self, run_id: UUID) -> None:
        # Database access is synchronous, so the work runs in a worker thread
        # and never blocks the event loop.
        await asyncio.to_thread(self.run_sync, run_id)

    def run_sync(self, run_id: UUID) -> None:
        # A session-level advisory lock survives stage commits, and is released
        # by PostgreSQL if this executor's connection/process dies.
        with (
            self._session_factory() as guard,
            guard.get_bind().connect() as connection,
        ):
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                {"key": f"paper-run:{run_id}"},
            )
            if not acquired:
                return
            connection.commit()
            stop = Event()
            lost = Event()

            def heartbeat() -> None:
                while not stop.wait(LEASE_SECONDS / 3):
                    try:
                        with self._session_factory() as session:
                            if not RunRepository(session).renew_lease(
                                run_id, lease_seconds=LEASE_SECONDS
                            ):
                                lost.set()
                                return
                    except Exception as exc:
                        lost.set()
                        logger.error(
                            "pipelines.run.heartbeat_failed",
                            error_type=type(exc).__name__,
                        )
                        return

            thread = Thread(target=heartbeat, daemon=True)
            thread.start()
            try:
                self._run_owned(run_id, lost)
            finally:
                stop.set()
                thread.join()
                connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                    {"key": f"paper-run:{run_id}"},
                )

    def _run_owned(self, run_id: UUID, lost: Event) -> None:
        session = self._session_factory()
        try:
            runs = RunRepository(session)
            papers = PaperRepository(session)
            chunks = ChunkRepository(session)

            run = runs.get(run_id)
            if run is None or not run.is_active:
                return
            paper = papers.get_paper(run.paper_id)
            if paper is None:
                runs.finish_failure(run_id, error_message="论文不存在")
                session.commit()
                return

            stage = run.current_stage or RunStage.PARSE
            while stage is not None:
                if lost.is_set():
                    session.rollback()
                    return
                runs.mark_stage_started(run_id, stage=stage)
                session.commit()
                runs.renew_lease(run_id, lease_seconds=LEASE_SECONDS)
                try:
                    self._run_stage(stage, papers=papers, chunks=chunks, paper=paper)
                except AppError as exc:
                    session.rollback()
                    runs.mark_stage_finished(run_id, stage=stage)
                    runs.finish_failure(run_id, error_message=exc.message)
                    session.commit()
                    logger.info(
                        "pipelines.run.stage_failed",
                        run_id=str(run_id),
                        stage=stage.value,
                        error_code=str(exc.code),
                    )
                    return
                except Exception as exc:  # unexpected: stop and record it
                    session.rollback()
                    runs.mark_stage_finished(run_id, stage=stage)
                    runs.finish_failure(run_id, error_message=type(exc).__name__)
                    session.commit()
                    logger.exception(
                        "pipelines.run.stage_crashed",
                        run_id=str(run_id),
                        stage=stage.value,
                        error_type=type(exc).__name__,
                    )
                    return
                if lost.is_set():
                    session.rollback()
                    return
                runs.mark_stage_finished(run_id, stage=stage)
                session.commit()
                stage = next_stage(stage)

            papers.lock_paper(run.paper_id)
            runs.finish_success(run_id)
            self._grant_entries(
                runs=runs, papers=papers, run_id=run_id, session=session
            )
            session.commit()
            logger.info("pipelines.run.finished", run_id=str(run_id))
        finally:
            session.close()

    # Stages ----------------------------------------------------------------
    def _run_stage(
        self,
        stage: RunStage,
        *,
        papers: PaperRepository,
        chunks: ChunkRepository,
        paper,
    ) -> None:
        if stage is RunStage.PARSE:
            self._parse_stage(papers, paper)
        elif stage is RunStage.CHUNK:
            self._chunking_stage(papers, chunks, paper)
        else:
            self._embedding_stage(chunks, paper.id)

    def _parse_stage(self, papers: PaperRepository, paper) -> None:
        """Parse unless a verified manifest says parse already succeeded."""
        if self._artifacts_verified(papers, paper):
            return
        with self._pdf_file(paper.file_hash) as pdf_path:
            artifact = self._mineru.parse(pdf_path=pdf_path)
        files: dict[str, dict] = {}

        def write(relative_path: str, payload: bytes) -> None:
            key = mineru_artifact_key(paper.file_hash, relative_path)
            self._storage.put_bytes(key, payload)
            files[relative_path] = {
                "key": key,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }

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
        # The manifest is written last: it is what makes the set complete.
        manifest = {
            "schema_version": 1,
            "file_hash": paper.file_hash,
            "parser_version": artifact.version,
            "files": files,
        }
        self._storage.put_bytes(
            mineru_artifact_key(paper.file_hash, MANIFEST_OBJECT),
            json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        )
        papers.publish_artifact(
            paper.id,
            manifest_key=mineru_artifact_key(paper.file_hash, MANIFEST_OBJECT),
            parser_version=artifact.version,
        )

    def _chunking_stage(
        self, papers: PaperRepository, chunks: ChunkRepository, paper
    ) -> None:
        raw = self._read_artifact(papers, paper, CONTENT_LIST_OBJECT)
        drafts = build_chunks(
            json.loads(raw),
            target_tokens=self._target_tokens,
            max_chars=self._max_chars,
        )
        if not drafts:
            raise AppError(
                "解析产物中没有可索引的内容",
                code=ErrorCode.IMPORT_ARTIFACT_INVALID,
                status_code=502,
            )
        chunks.replace_chunks(paper_id=paper.id, drafts=drafts)

    def _embedding_stage(self, chunks: ChunkRepository, paper_id: UUID) -> None:
        embeddings = self._embeddings
        if not embeddings.is_configured:
            raise AppError(
                "向量服务未配置",
                code=ErrorCode.PROVIDER_NOT_CONFIGURED,
                status_code=503,
            )
        pending = chunks.pending_embedding_chunks(paper_id)
        if not pending:
            return
        vectors = embeddings.embed_documents([chunk.content for chunk in pending])
        for chunk, vector in zip(pending, vectors, strict=True):
            chunks.set_embedding(
                chunk_id=chunk.id,
                embedding=vector,
                model=embeddings.model,
            )

    # Artifact checks -------------------------------------------------------
    def _artifacts_verified(self, papers: PaperRepository, paper) -> bool:
        """Whether the published manifest still matches every stored file.

        A flag on the paper is not enough: a run killed mid-write leaves files
        that no longer match the manifest they are named in.
        """
        if not paper.artifact_manifest_key:
            return False
        try:
            manifest = json.loads(self._storage.read_text(paper.artifact_manifest_key))
        except (FileNotFoundError, ValueError):
            return False
        if manifest.get("file_hash") != paper.file_hash:
            return False
        files = manifest.get("files")
        if not isinstance(files, dict):
            return False
        for entry in files.values():
            if not isinstance(entry, dict):
                return False
            key, digest = entry.get("key"), entry.get("sha256")
            if not isinstance(key, str) or not isinstance(digest, str):
                return False
            try:
                raw = self._storage.read_bytes(key)
            except FileNotFoundError:
                return False
            if hashlib.sha256(raw).hexdigest() != digest:
                return False
        return True

    def _read_artifact(self, papers: PaperRepository, paper, name: str) -> bytes:
        """Read one artifact whose manifest the parse stage already verified."""
        refreshed = papers.get_paper(paper.id) or paper
        if not refreshed.artifact_manifest_key:
            raise AppError(
                "解析产物缺失",
                code=ErrorCode.IMPORT_ARTIFACT_INVALID,
                status_code=502,
            )
        manifest = json.loads(self._storage.read_text(refreshed.artifact_manifest_key))
        return self._storage.read_bytes(manifest["files"][name]["key"])

    # Entries ---------------------------------------------------------------
    def _grant_entries(
        self,
        *,
        runs: RunRepository,
        papers: PaperRepository,
        run_id: UUID,
        session: Session,
    ) -> None:
        """Everyone who asked for this paper may now see it."""
        run = runs.get(run_id)
        if run is None:
            return
        for request in runs.requests_of_run(run_id):
            entry = papers.link_paper(user_id=request.user_id, paper_id=run.paper_id)
            # The entry must exist first: a project holds the user's entries.
            if request.project_id is not None:
                ProjectRepository(session).add_papers(
                    project_id=request.project_id, user_paper_ids=[entry.id]
                )

    @contextmanager
    def _pdf_file(self, file_hash: str) -> Iterator[Path]:
        """PDF 在本地实现下是零拷贝；S3 实现会下载到临时文件。"""
        with self._storage.materialize(paper_pdf_key(file_hash)) as path:
            yield path


def build_run_pipeline(
    *,
    storage: ObjectStorage,
    session_factory: SessionFactory,
    scheduler: TaskScheduler,
) -> RunPipeline:
    return RunPipeline(
        scheduler=scheduler,
        session_factory=session_factory,
        storage=storage,
        mineru=MineruParser(
            base_url=settings.mineru_api_url,
            api_key=settings.mineru_api_key,
            timeout_seconds=settings.mineru_timeout_seconds,
        ),
        embeddings=build_embedding_adapter(),
        target_tokens=settings.chunk_token_num,
        max_chars=settings.chunk_max_chars,
    )
