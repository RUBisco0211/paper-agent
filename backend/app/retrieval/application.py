from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError

from ..library.persistence import PaperRepository
from ..platform.errors import ErrorCode, NotFoundError
from ..projects.persistence import ProjectRepository
from .domain import (
    ChannelReport,
    ChannelStatus,
    Evidence,
    SearchOutcome,
    SearchScope,
    SearchStatus,
)
from .embedding import EmbeddingClient
from .fusion import apply_budgets, reciprocal_rank_fusion
from .persistence import ChunkRepository

logger = structlog.get_logger(__name__)

SNIPPET_MAX_CHARS = 1200
EVIDENCE_MAX_CHARS = 6000


class SearchService:
    """Authorized hybrid retrieval: keyword + vector recall, RRF fusion."""

    def __init__(
        self,
        chunks: ChunkRepository,
        papers: PaperRepository,
        projects: ProjectRepository,
        embeddings: EmbeddingClient,
        *,
        keyword_top_n: int,
        vector_top_n: int,
        rrf_k: int,
        max_evidence: int,
        max_evidence_per_paper: int,
    ) -> None:
        self._chunks = chunks
        self._papers = papers
        self._projects = projects
        self._embeddings = embeddings
        self._keyword_top_n = keyword_top_n
        self._vector_top_n = vector_top_n
        self._rrf_k = rrf_k
        self._max_evidence = max_evidence
        self._max_evidence_per_paper = max_evidence_per_paper

    def search(
        self,
        *,
        user_id: UUID,
        query: str,
        scope: SearchScope,
        limit: int,
        project_id: UUID | None = None,
        paper_ids: list[UUID] | None = None,
    ) -> SearchOutcome:
        authorized = self._authorized_scope(
            user_id=user_id,
            scope=scope,
            project_id=project_id,
            paper_ids=paper_ids,
        )
        shared_paper_ids = list(authorized)
        if not shared_paper_ids:
            return SearchOutcome(
                status=SearchStatus.OK,
                evidence=[],
                channels={
                    "keyword": ChannelReport(
                        channel="keyword",
                        status=ChannelStatus.OK,
                        result_count=0,
                        detail="授权范围内没有可检索的全文",
                    ),
                    "vector": ChannelReport(
                        channel="vector",
                        status=ChannelStatus.SKIPPED,
                        result_count=0,
                        detail="授权范围内没有可检索的全文",
                    ),
                },
            )

        reports: dict[str, ChannelReport] = {}
        keyword_matches = self._keyword_channel(shared_paper_ids, query, reports)
        vector_matches = self._vector_channel(shared_paper_ids, query, reports)

        fused = reciprocal_rank_fusion(
            keyword_matches,
            vector_matches,
            k=self._rrf_k,
        )
        evidence = apply_budgets(
            fused,
            max_evidence=min(limit, self._max_evidence),
            max_per_paper=self._max_evidence_per_paper,
            max_chars=EVIDENCE_MAX_CHARS,
        )
        logger.info(
            "service.retrieval.searched",
            user_id=str(user_id),
            scope=scope.value,
            keyword_count=len(keyword_matches),
            vector_count=len(vector_matches),
            evidence_count=len(evidence),
        )
        # Evidence leaves the module with user-visible entry ids only; the
        # shared paper id never reaches a client.
        return SearchOutcome(
            status=_overall_status(reports),
            evidence=[_user_facing(_trim(item), authorized) for item in evidence],
            channels=reports,
        )

    # Channels --------------------------------------------------------------
    def _keyword_channel(
        self,
        paper_ids: list[UUID],
        query: str,
        reports: dict[str, ChannelReport],
    ) -> list:
        try:
            matches = self._chunks.search_keyword(
                paper_ids=paper_ids,
                query=query,
                limit=self._keyword_top_n,
            )
        except SQLAlchemyError as exc:
            logger.error(
                "service.retrieval.keyword_failed",
                error_type=type(exc).__name__,
            )
            reports["keyword"] = ChannelReport(
                channel="keyword",
                status=ChannelStatus.UNAVAILABLE,
                result_count=0,
                detail="关键词检索通道不可用",
            )
            return []
        reports["keyword"] = ChannelReport(
            channel="keyword",
            status=ChannelStatus.OK,
            result_count=len(matches),
        )
        return matches

    def _vector_channel(
        self,
        paper_ids: list[UUID],
        query: str,
        reports: dict[str, ChannelReport],
    ) -> list:
        if not self._embeddings.is_configured:
            reports["vector"] = ChannelReport(
                channel="vector",
                status=ChannelStatus.SKIPPED,
                result_count=0,
                detail="实例未配置 Embedding 服务，本次只有关键词召回",
            )
            return []
        try:
            vectors = self._embeddings.embed([query])
        except Exception as exc:  # provider errors carry stable codes already
            logger.warning(
                "service.retrieval.embedding_failed",
                error_type=type(exc).__name__,
            )
            reports["vector"] = ChannelReport(
                channel="vector",
                status=ChannelStatus.DEGRADED,
                result_count=0,
                detail="向量召回本次不可用",
            )
            return []

        try:
            matches = self._chunks.search_vector(
                paper_ids=paper_ids,
                embedding=vectors[0],
                model=self._embeddings.model,
                limit=self._vector_top_n,
            )
        except SQLAlchemyError as exc:
            logger.error(
                "service.retrieval.vector_failed",
                error_type=type(exc).__name__,
            )
            reports["vector"] = ChannelReport(
                channel="vector",
                status=ChannelStatus.UNAVAILABLE,
                result_count=0,
                detail="向量检索通道不可用",
            )
            return []
        reports["vector"] = ChannelReport(
            channel="vector",
            status=ChannelStatus.OK,
            result_count=len(matches),
        )
        return matches

    # Scope -----------------------------------------------------------------
    def _authorized_scope(
        self,
        *,
        user_id: UUID,
        scope: SearchScope,
        project_id: UUID | None,
        paper_ids: list[UUID] | None,
    ) -> dict[UUID, UUID]:
        """Return ``paper_id -> user_paper_id`` after authorization."""
        if scope is SearchScope.PROJECT:
            if project_id is None:
                raise NotFoundError(
                    "项目不存在",
                    code=ErrorCode.PROJECT_NOT_FOUND,
                )
            project = self._projects.get_project(project_id)
            if project is None or project.user_id != user_id:
                raise NotFoundError("项目不存在", code=ErrorCode.PROJECT_NOT_FOUND)
            member_ids = list(self._projects.paper_ids_of(project_id))
            return self._papers.paper_scope_of_entries(
                user_id=user_id,
                user_paper_ids=member_ids,
            )

        if scope is SearchScope.PAPER:
            requested = paper_ids or []
            if not requested:
                raise NotFoundError("论文不存在", code=ErrorCode.PAPER_NOT_FOUND)
            owned = self._papers.user_papers_by_ids(
                user_id=user_id,
                user_paper_ids=requested,
            )
            if len(owned) != len(set(requested)):
                raise NotFoundError("论文不存在", code=ErrorCode.PAPER_NOT_FOUND)
            return self._papers.paper_scope_of_entries(
                user_id=user_id,
                user_paper_ids=requested,
            )

        return self._papers.paper_scope_for_user(user_id)


def _overall_status(reports: dict[str, ChannelReport]) -> SearchStatus:
    statuses = {report.status for report in reports.values()}
    if statuses == {ChannelStatus.OK}:
        return SearchStatus.OK
    if ChannelStatus.OK in statuses:
        return SearchStatus.DEGRADED
    return SearchStatus.UNAVAILABLE


def _user_facing(evidence: Evidence, authorized: dict[UUID, UUID]) -> Evidence:
    return Evidence(
        paper_id=authorized.get(evidence.paper_id, evidence.paper_id),
        chunk_ids=evidence.chunk_ids,
        title_path=evidence.title_path,
        snippet=evidence.snippet,
        page_start=evidence.page_start,
        page_end=evidence.page_end,
        score=evidence.score,
        chunk_index=evidence.chunk_index,
        keyword_rank=evidence.keyword_rank,
        vector_rank=evidence.vector_rank,
    )


def _trim(evidence: Evidence) -> Evidence:
    if len(evidence.snippet) <= SNIPPET_MAX_CHARS:
        return evidence
    return Evidence(
        paper_id=evidence.paper_id,
        chunk_ids=evidence.chunk_ids,
        title_path=evidence.title_path,
        snippet=evidence.snippet[:SNIPPET_MAX_CHARS],
        page_start=evidence.page_start,
        page_end=evidence.page_end,
        score=evidence.score,
        chunk_index=evidence.chunk_index,
        keyword_rank=evidence.keyword_rank,
        vector_rank=evidence.vector_rank,
    )
