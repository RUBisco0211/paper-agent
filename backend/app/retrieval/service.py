import base64
from dataclasses import replace
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError

from app.literature_support.evidence.citations import build_citation_id
from app.literature_support.evidence.ranking import (
    apply_budgets,
    reciprocal_rank_fusion,
)

from ..library.repo import PaperRepository
from ..library.service import PaperLibraryService
from ..platform.errors import ErrorCode, NotFoundError
from ..projects.repo import ProjectRepository
from ..retrieval.ports import EmbeddingAdapter
from ..sessions.service import SessionBindingService
from .domain import (
    ChannelReport,
    ChannelStatus,
    Evidence,
    SearchOutcome,
    SearchScope,
    SearchStatus,
)
from .repo import ChunkRepository

logger = structlog.get_logger(__name__)


class BoundSearchService:
    """Resolve immutable session scope before executing business retrieval."""

    def __init__(
        self, bindings: SessionBindingService, search: "SearchService"
    ) -> None:
        self._bindings = bindings
        self._search = search

    def search(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        query: str,
        limit: int,
    ) -> tuple[SearchOutcome, SearchScope]:
        binding = self._bindings.require(session_id=session_id, user_id=user_id)
        scope = (
            SearchScope.PROJECT
            if binding.project_id is not None
            else SearchScope.LIBRARY
        )
        outcome = self._search.search(
            user_id=user_id,
            query=query,
            scope=scope,
            project_id=binding.project_id,
            limit=limit,
        )
        for evidence in outcome.evidence:
            self._bindings.record_citation(
                session_id=session_id,
                citation_id=build_citation_id(evidence.chunk_ids),
                user_paper_id=evidence.paper_id,
                chunk_ids=evidence.chunk_ids,
                title_path=evidence.title_path,
                snippet=evidence.snippet,
                page_start=evidence.page_start,
                page_end=evidence.page_end,
                source_locations=flatten_source_locations(
                    self._search.source_locations(evidence.chunk_ids)
                ),
            )
        return outcome, scope


def flatten_source_locations(locations: list[dict]) -> list[dict]:
    """Collapse chunk grouping into one ordered block list for locating the evidence."""
    merged: dict[int, dict] = {}
    for location in locations:
        for source in location.get("source_ranges") or []:
            block_id = source.get("block_id")
            if not isinstance(block_id, int):
                continue
            start = source.get("char_start")
            end = source.get("char_end")
            existing = merged.get(block_id)
            if existing is None:
                merged[block_id] = {
                    "block_id": block_id,
                    "page": source.get("page"),
                    "bbox": source.get("bbox"),
                    "char_start": start,
                    "char_end": end,
                }
                continue
            if isinstance(start, int):
                existing["char_start"] = (
                    start
                    if existing["char_start"] is None
                    else min(existing["char_start"], start)
                )
            if isinstance(end, int):
                existing["char_end"] = (
                    end if existing["char_end"] is None else max(existing["char_end"], end)
                )
    return [merged[block_id] for block_id in sorted(merged)]


class BoundPaperService:
    def __init__(
        self,
        bindings: SessionBindingService,
        library: PaperLibraryService,
        projects: ProjectRepository,
    ) -> None:
        self._bindings = bindings
        self._library = library
        self._projects = projects

    def resolve_quote(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        user_paper_id: UUID,
        kind: str,
        version: str,
        page: int,
        block_id: int | None,
        start: int | None,
        end: int | None,
        selected_text: str,
        include_image: bool = False,
    ) -> dict:
        binding = self._bindings.require(session_id=session_id, user_id=user_id)
        entry = self._library.get_entry(user_id=user_id, user_paper_id=user_paper_id)
        if entry is None or (
            binding.project_id is not None
            and user_paper_id not in self._projects.paper_ids_of(binding.project_id)
        ):
            raise NotFoundError("文献不在当前会话范围", code=ErrorCode.PAPER_NOT_FOUND)
        if kind == "parsed_block":
            if version != self._library.artifact_cache_version(
                user_id=user_id, user_paper_id=user_paper_id
            ):
                raise ValueError("artifact_version_changed")
            if block_id is None or start is None or end is None:
                raise ValueError("selection_mismatch")
            block = self._library.get_block(
                user_id=user_id, user_paper_id=user_paper_id, block_id=block_id
            )
            text = self._library.get_block_full_text(
                user_id=user_id, user_paper_id=user_paper_id, block_id=block_id
            )
            source_text = text or block.get("formula") or ""
            if (
                block["page"] != page
                or source_text[start:end] != selected_text
                or (not include_image and end <= start)
            ):
                raise ValueError("selection_mismatch")
            if include_image:
                if block["type"] not in {"image", "chart"} or not block["has_image"]:
                    raise ValueError("image_unavailable")
                payload, media_type = self._library.get_block_image(
                    user_id=user_id, user_paper_id=user_paper_id, block_id=block_id
                )
                if len(payload) > 5 * 1024 * 1024 or media_type not in {
                    "image/png",
                    "image/jpeg",
                    "image/webp",
                    "image/gif",
                }:
                    raise ValueError("image_unsupported")
                return {
                    "title": entry.user_paper.title,
                    "page": page,
                    "image_base64": base64.b64encode(payload).decode("ascii"),
                    "image_media_type": media_type,
                }
        elif kind == "pdf_selection":
            if include_image:
                raise ValueError("image_unavailable")
            if version != self._library.pdf_cache_version(
                user_id=user_id, user_paper_id=user_paper_id
            ):
                raise ValueError("pdf_version_changed")
            if entry.paper is None or page > entry.paper.page_count:
                raise ValueError("page_out_of_range")
        else:
            raise ValueError("unsupported_quote_kind")
        return {"title": entry.user_paper.title, "page": page}

    def list_papers(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[str, int, list[dict]]:
        binding = self._bindings.require(session_id=session_id, user_id=user_id)
        if binding.project_id is None:
            entries, total = self._library.list_entries(
                user_id=user_id,
                limit=limit,
                offset=offset,
            )
            scope = "library"
        else:
            member_ids = list(self._projects.paper_ids_of(binding.project_id))
            all_entries = self._library.entries_for(
                user_id=user_id,
                user_paper_ids=member_ids,
            )
            total = len(all_entries)
            entries = all_entries[offset : offset + limit]
            scope = "project"
        return (
            scope,
            total,
            [
                {
                    "paper_id": str(entry.user_paper.id),
                    "title": entry.user_paper.title,
                    "authors": entry.user_paper.authors[:5],
                    "year": entry.user_paper.year,
                    "venue": entry.user_paper.venue,
                    "has_fulltext": entry.capabilities.has_fulltext,
                }
                for entry in entries
            ],
        )


class SearchService:
    """Authorized hybrid retrieval: keyword + vector recall, RRF fusion."""

    def __init__(
        self,
        chunks: ChunkRepository,
        papers: PaperRepository,
        projects: ProjectRepository,
        embeddings: EmbeddingAdapter,
        *,
        keyword_top_n: int,
        vector_top_n: int,
        rrf_k: int,
        max_evidence: int,
        max_evidence_per_paper: int,
        evidence_max_chars: int,
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
        self._evidence_max_chars = evidence_max_chars

    def source_locations(self, chunk_ids: list[UUID]) -> list[dict]:
        return self._chunks.source_locations(chunk_ids)

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
            max_chars=self._evidence_max_chars,
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
            evidence=[_user_facing(item, authorized) for item in evidence],
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
            vector = self._embeddings.embed_query(query)
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
                embedding=vector,
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
    return replace(
        evidence,
        paper_id=authorized.get(evidence.paper_id, evidence.paper_id),
    )
