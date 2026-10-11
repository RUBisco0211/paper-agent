from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.literature_support.evidence.citations import build_citation_id

from ..auth.depends import CurrentUser
from ..platform.internal_auth import AgentInternalAuth
from .depends import (
    BoundPaperServiceDep,
    BoundSearchServiceDep,
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
    EvidenceRead,
    QuoteReferenceResolved,
    QuoteReferenceResolveRequest,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(tags=["retrieval"])


@router.post("/internal/quote-reference/resolve", response_model=QuoteReferenceResolved)
def resolve_quote_reference(
    payload: QuoteReferenceResolveRequest,
    _auth: AgentInternalAuth,
    service: BoundPaperServiceDep,
) -> QuoteReferenceResolved:
    from fastapi import HTTPException

    try:
        return QuoteReferenceResolved(
            **service.resolve_quote(
                user_id=payload.user_id,
                session_id=payload.session_id,
                user_paper_id=payload.user_paper_id,
                kind=payload.kind,
                version=payload.version,
                page=payload.page,
                block_id=payload.block_id,
                start=payload.start,
                end=payload.end,
                selected_text=payload.selected_text,
                include_image=payload.include_image,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    return BoundListResponse.model_validate(
        {"scope": scope, "total": total, "papers": papers}
    )


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
