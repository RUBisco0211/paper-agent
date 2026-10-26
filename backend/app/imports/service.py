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
from app.platform.errors import (
    AppError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.platform.security import create_candidate_token, read_candidate_token
from app.projects.repo import ProjectRecord, ProjectRepository
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

    def start(
        self,
        *,
        user_id: UUID,
        identifier_text: str,
        project_id: UUID | None = None,
    ) -> Download:
        """Queue one download, remembering the project it should also join.

        The project is checked now, not when the file finally arrives: naming
        someone else's project must fail while the user is still looking.
        """
        identifier = parse_identifier(identifier_text)
        session = self._session_factory()
        try:
            if project_id is not None:
                owned = session.scalar(
                    select(ProjectRecord.id)
                    .where(ProjectRecord.id == project_id)
                    .where(ProjectRecord.user_id == user_id)
                )
                if owned is None:
                    raise NotFoundError(
                        "项目不存在", code=ErrorCode.PROJECT_NOT_FOUND
                    )
            repository = ImportRepository(session)
            download = repository.add_download(
                user_id=user_id,
                identifier_type=identifier.type.value,
                identifier=identifier.value,
                project_id=project_id,
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
        """Every request this user made, newest first, with its run's progress.

        An upload has no download row, so the queue is the union of the two:
        requests carry the paper, downloads carry the fetching step. When a
        download points at a run, that download already speaks for it and the
        request must not appear twice.
        """
        session = self._session_factory()
        try:
            downloads = DownloadRepository(session).list_for_user(
                user_id=user_id, limit=limit
            )
            requests = RunRepository(session).list_requests_for_user(
                user_id=user_id, limit=limit
            )
            claimed_runs = {item.run_id for item in downloads if item.run_id}
            paper_ids = list(
                {item.paper_id for item in downloads if item.paper_id}
                | {item.paper_id for item in requests if item.paper_id}
            )
            runs = RunRepository(session).latest_for_papers(paper_ids)

            items: list[dict] = []
            for item in downloads:
                run = runs.get(item.paper_id) if item.paper_id else None
                items.append(
                    {
                        "source": "download",
                        "id": str(item.id),
                        "identifier": item.identifier,
                        "identifier_type": item.identifier_type,
                        "status": item.status.value,
                        "paper_id": str(item.paper_id) if item.paper_id else None,
                        "run_id": str(item.run_id) if item.run_id else None,
                        "project_id": (
                            str(item.project_id) if item.project_id else None
                        ),
                        "error_message": item.error_message,
                        "created_at": item.created_at.isoformat(),
                        "run": _run_view(run),
                    }
                )
            seen_requests: set[tuple[UUID, UUID]] = set()
            for request in requests:
                if request.run_id in claimed_runs:
                    continue
                # One row per request, even when two requests share a run.
                key = (request.user_id, request.run_id)
                if key in seen_requests:
                    continue
                seen_requests.add(key)
                run = runs.get(request.paper_id) if request.paper_id else None
                items.append(
                    {
                        "source": "request",
                        "id": str(request.run_id),
                        "identifier": "",
                        "identifier_type": "upload",
                        "status": run.status.value if run else "pending",
                        "paper_id": (
                            str(request.paper_id) if request.paper_id else None
                        ),
                        "run_id": (
                            str(request.run_id) if request.run_id else None
                        ),
                        "project_id": (
                            str(request.project_id) if request.project_id else None
                        ),
                        "error_message": run.error_message if run else None,
                        "created_at": (
                            request.created_at.isoformat()
                            if request.created_at
                            else ""
                        ),
                        "run": _run_view(run),
                    }
                )
            items.sort(key=lambda entry: entry["created_at"], reverse=True)
            return items[:limit]
        finally:
            session.close()


def _run_view(run) -> dict | None:
    if run is None:
        return None
    return {
        "status": run.status.value,
        "stage": run.current_stage.value if run.current_stage else None,
        "error_message": run.error_message,
    }
