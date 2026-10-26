"""Import entry points: ask for a download, or approve a discovered batch.

Nothing here parses or downloads. A request records intent and a worker takes
it from there, so a slow source never holds an HTTP connection and a batch of
requests never has to finish inside one.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select

from app.literature_support.scholar.identifiers import parse_identifier
from app.platform.database import SessionFactory
from app.platform.errors import AppError, ForbiddenError, ValidationError
from app.platform.security import create_candidate_token, read_candidate_token
from app.projects.repo import ProjectRepository
from app.sessions.repo import SessionBindingRepository
from app.sessions.service import SessionBindingService

from ..pipelines.domain import Download
from ..pipelines.repo import DownloadRepository, RunRepository
from .ports import PaperDiscoveryAdapter
from .repo import ImportApprovalRecord, ImportRepository

logger = structlog.get_logger(__name__)


class DiscoveryService:
    def __init__(
        self, bindings: SessionBindingService, provider: PaperDiscoveryAdapter
    ) -> None:
        self._bindings = bindings
        self._provider = provider

    def search_manual(self, *, query: str, limit: int) -> dict:
        result = self._provider.search(query, limit)
        return {"papers": result.papers, "failed_sources": result.failed_sources}

    def search(
        self, *, user_id: UUID, session_id: UUID, query: str, limit: int
    ) -> dict:
        self._bindings.require(session_id=session_id, user_id=user_id)
        result = self._provider.search(query, limit)
        candidates = result.papers
        for candidate in candidates:
            identifier = candidate.get("doi")
            source_id = candidate.get("source_id")
            try:
                if not isinstance(identifier, str) or not isinstance(source_id, str):
                    continue
                parse_identifier(identifier)
            except AppError:
                continue
            candidate["candidate_token"] = create_candidate_token(
                user_id=str(user_id),
                session_id=str(session_id),
                source_id=source_id,
                identifier=identifier,
                title=candidate.get("title")
                if isinstance(candidate.get("title"), str)
                else None,
            )
        return {"papers": candidates, "failed_sources": result.failed_sources}


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
            source_id = claims.get("source_id")
            if not isinstance(source_id, str) or not source_id.startswith("https://"):
                raise ValidationError("候选文献信息无效")
            if identifier.value in seen:
                continue
            seen.add(identifier.value)
            candidates.append(
                {
                    "identifier": identifier.value,
                    "source_id": source_id,
                    "title": claims.get("title")
                    if isinstance(claims.get("title"), str)
                    else None,
                }
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
            SessionBindingService(
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
                    )
                    results.append(
                        {
                            "identifier": candidate["identifier"],
                            "download_id": str(item.id),
                            "status": str(item.status.value),
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

    def preview(self, *, user_id: UUID, session_id: UUID) -> list[dict]:
        with self._session_factory() as session:
            SessionBindingService(
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
            )
            if (
                record is None
                or record.status != "pending"
                or record.expires_at < datetime.now(UTC)
            ):
                raise ForbiddenError("本次选文授权已失效，请重新选择")
            return [
                {
                    "title": item.get("title"),
                    "identifier": item["identifier"],
                    "source_id": item["source_id"],
                }
                for item in record.candidates
            ]


class ImportService:
    """Record what a user asked for; the worker owns fetching and processing."""

    def __init__(self, *, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def start(self, *, user_id: UUID, identifier_text: str) -> Download:
        """Queue one download. An already-held paper gets an entry, no download."""
        identifier = parse_identifier(identifier_text)
        session = self._session_factory()
        try:
            repository = ImportRepository(session)
            download = repository.add_download(
                user_id=user_id,
                identifier_type=identifier.type.value,
                identifier=identifier.value,
            )
            session.commit()
            logger.info(
                "imports.download.queued",
                download_id=str(download.id),
                identifier_type=identifier.type.value,
            )
            return download
        finally:
            session.close()

    def queue(self, *, user_id: UUID, limit: int = 100) -> list[dict]:
        """This user's requests, newest first, each with its run's progress."""
        with self._session_factory() as session:
            downloads = DownloadRepository(session).list_for_user(
                user_id=user_id, limit=limit
            )
            paper_ids = [item.paper_id for item in downloads if item.paper_id]
            runs = RunRepository(session).latest_for_papers(paper_ids)
            items: list[dict] = []
            for item in downloads:
                run = runs.get(item.paper_id) if item.paper_id else None
                items.append(
                    {
                        "id": str(item.id),
                        "identifier": item.identifier,
                        "identifier_type": item.identifier_type,
                        "status": item.status.value,
                        "paper_id": str(item.paper_id) if item.paper_id else None,
                        "run_id": str(item.run_id) if item.run_id else None,
                        "source_url": item.source_url,
                        "error_message": item.error_message,
                        "created_at": item.created_at.isoformat(),
                        "finished_at": (
                            item.finished_at.isoformat() if item.finished_at else None
                        ),
                        "run": (
                            {
                                "status": run.status.value,
                                "stage": (
                                    run.current_stage.value
                                    if run.current_stage
                                    else None
                                ),
                                "error_message": run.error_message,
                            }
                            if run is not None
                            else None
                        ),
                    }
                )
            return items
