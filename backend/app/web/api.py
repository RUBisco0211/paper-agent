"""HTTP boundary for public web access, used only by the agent service."""

from fastapi import APIRouter

from ..platform.internal_auth import AgentInternalAuth
from .depends import WebSearchServiceDep
from .schemas import WebExcerptRequest, WebFetchRequest, WebSearchRequest

internal_router = APIRouter(tags=["web"])


@internal_router.post("/internal/web-search")
def web_search(
    payload: WebSearchRequest,
    _auth: AgentInternalAuth,
    service: WebSearchServiceDep,
) -> dict:
    return service.search(payload.user_id, payload.query, payload.max_results)


@internal_router.post("/internal/web-fetch")
def web_fetch(
    payload: WebFetchRequest,
    _auth: AgentInternalAuth,
    service: WebSearchServiceDep,
) -> dict:
    return service.fetch(
        payload.user_id, payload.url, payload.offset, payload.max_chars
    )


@internal_router.post("/internal/web-extract-excerpt")
def web_extract_excerpt(
    payload: WebExcerptRequest,
    _auth: AgentInternalAuth,
    service: WebSearchServiceDep,
) -> dict:
    return service.excerpt(payload.user_id, payload.url, payload.query, payload.chunks)
