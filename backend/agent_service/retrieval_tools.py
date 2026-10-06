"""Session-bound read-only paper tools backed by the business HTTP API."""

from uuid import UUID

import httpx
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool, ToolBase

from app.platform.config import settings


class PaperReadTool(FunctionTool):
    async def check_permissions(self, *_args, **_kwargs) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW)


async def build_retrieval_tools(
    user_id: str,
    agent_id: str,
    session_id: str,
) -> list[ToolBase]:
    """Bind immutable identity and scope lookup to tools, not model arguments."""
    del agent_id
    UUID(user_id)
    UUID(session_id)

    async def request(method: str, path: str, **kwargs) -> dict:
        if not settings.agent_internal_key:
            raise RuntimeError("AGENT_INTERNAL_KEY is required for retrieval tools")
        async with httpx.AsyncClient(
            base_url=settings.business_api_url.rstrip("/"),
            timeout=20.0,
        ) as client:
            response = await client.request(
                method,
                f"{settings.api_prefix}/internal/{path}",
                headers={"X-Agent-Internal-Key": settings.agent_internal_key},
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    async def list_papers(limit: int = 20, offset: int = 0) -> dict:
        """List papers in this session's authorized library or project scope."""
        return await request(
            "GET",
            "papers",
            params={
                "user_id": user_id,
                "session_id": session_id,
                "limit": max(1, min(limit, 50)),
                "offset": max(offset, 0),
            },
        )

    async def search_papers(query: str, limit: int = 8) -> dict:
        """Search paper evidence in this session; returns registered citation IDs."""
        return await request(
            "POST",
            "search",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "query": query,
                "limit": max(1, min(limit, 20)),
            },
        )

    async def get_paper_excerpt(citation_id: str) -> dict:
        """Read the registered original excerpt and page for a citation ID."""
        return await request(
            "GET",
            "excerpt",
            params={
                "user_id": user_id,
                "session_id": session_id,
                "citation_id": citation_id,
            },
        )

    return [
        PaperReadTool(func, is_read_only=True, is_concurrency_safe=True)
        for func in (list_papers, search_papers, get_paper_excerpt)
    ]
