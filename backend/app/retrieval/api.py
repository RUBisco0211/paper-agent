from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from ..auth.depends import CurrentUser
from ..evidence.citations import build_citation_id
from .depends import (
    AgentInternalAuth,
    BoundPaperServiceDep,
    BoundSearchServiceDep,
    DiscoveryServiceDep,
    SearchServiceDep,
)
from .domain import SearchOutcome
from .schemas import (
    BoundEvidenceRead,
    BoundExcerptResponse,
    BoundListResponse,
    BoundSearchRequest,
    BoundSearchResponse,
    ChannelRead,
    DiscoveryRequest,
    DiscoveryResponse,
    EvidenceRead,
    ManualDiscoveryRequest,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(tags=["retrieval"])


@router.post("/discover-papers", response_model=DiscoveryResponse)
def discover_papers_manually(
    payload: ManualDiscoveryRequest,
    _user: CurrentUser,
    service: DiscoveryServiceDep,
) -> DiscoveryResponse:
    return DiscoveryResponse(
        **service.search_manual(query=payload.query, limit=payload.limit)
    )


@router.post("/internal/discover-papers", response_model=DiscoveryResponse)
def discover_papers(
    payload: DiscoveryRequest,
    _auth: AgentInternalAuth,
    service: DiscoveryServiceDep,
) -> DiscoveryResponse:
    return DiscoveryResponse(
        **service.search(
            user_id=payload.user_id,
            session_id=payload.session_id,
            query=payload.query,
            limit=payload.limit,
        )
    )


@router.get("/internal/papers", response_model=BoundListResponse)
def list_bound_papers(
    user_id: UUID,
    session_id: UUID,
    _auth: AgentInternalAuth,
    service: BoundPaperServiceDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BoundListResponse:
    scope, total, papers = service.list_papers(
        user_id=user_id,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return BoundListResponse(scope=scope, total=total, papers=papers)


@router.get("/internal/excerpt", response_model=BoundExcerptResponse)
def get_bound_excerpt(
    user_id: UUID,
    session_id: UUID,
    citation_id: str,
    _auth: AgentInternalAuth,
    service: BoundPaperServiceDep,
) -> BoundExcerptResponse:
    return BoundExcerptResponse(
        **service.get_excerpt(
            user_id=user_id,
            session_id=session_id,
            citation_id=citation_id,
        )
    )


@router.post("/internal/search", response_model=BoundSearchResponse)
def search_bound_session(
    payload: BoundSearchRequest,
    _auth: AgentInternalAuth,
    service: BoundSearchServiceDep,
) -> BoundSearchResponse:
    outcome, scope = service.search(
        user_id=payload.user_id,
        session_id=payload.session_id,
        query=payload.query,
        limit=payload.limit,
    )
    return BoundSearchResponse(
        scope=scope,
        status=outcome.status,
        channels={
            name: ChannelRead(
                status=report.status,
                result_count=report.result_count,
                detail=report.detail,
            )
            for name, report in outcome.channels.items()
        },
        evidence=[
            BoundEvidenceRead(
                paper_id=item.paper_id,
                chunk_ids=item.chunk_ids,
                title_path=item.title_path,
                snippet=item.snippet,
                page_start=item.page_start,
                page_end=item.page_end,
                score=item.score,
                keyword_rank=item.keyword_rank,
                vector_rank=item.vector_rank,
                citation_id=build_citation_id(item.chunk_ids),
            )
            for item in outcome.evidence
        ],
    )


def _to_response(outcome: SearchOutcome, request: SearchRequest) -> SearchResponse:
    return SearchResponse(
        query=request.query,
        scope=request.scope,
        status=outcome.status,
        channels={
            name: ChannelRead(
                status=report.status,
                result_count=report.result_count,
                detail=report.detail,
            )
            for name, report in outcome.channels.items()
        },
        evidence=[
            EvidenceRead(
                paper_id=item.paper_id,
                chunk_ids=item.chunk_ids,
                title_path=item.title_path,
                snippet=item.snippet,
                page_start=item.page_start,
                page_end=item.page_end,
                score=item.score,
                keyword_rank=item.keyword_rank,
                vector_rank=item.vector_rank,
            )
            for item in outcome.evidence
        ],
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="可测试的混合检索入口（不做独立搜索页）",
)
def search(
    payload: SearchRequest,
    user: CurrentUser,
    service: SearchServiceDep,
) -> SearchResponse:
    outcome = service.search(
        user_id=user.id,
        query=payload.query,
        scope=payload.scope,
        limit=payload.limit,
        project_id=payload.project_id,
        paper_ids=payload.paper_ids,
    )
    return _to_response(outcome, payload)
