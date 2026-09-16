from fastapi import APIRouter

from ..auth.dependencies import CurrentUser
from .dependencies import SearchServiceDep
from .domain import SearchOutcome
from .schemas import ChannelRead, EvidenceRead, SearchRequest, SearchResponse

router = APIRouter(tags=["retrieval"])


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
