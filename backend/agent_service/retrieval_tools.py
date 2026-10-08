"""Session-bound read-only paper tools backed by the business HTTP API."""

from uuid import UUID

import httpx
from agentscope.app.storage import SessionSource, StorageBase
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool, ToolBase

from app.platform.config import settings


class PaperReadTool(FunctionTool):
    async def check_permissions(self, *_args, **_kwargs) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW)


class ApprovedImportTool(FunctionTool):
    async def check_permissions(self, *_args, **_kwargs) -> PermissionDecision:
        # The business service enforces a previously confirmed, single-use batch.
        return PermissionDecision(behavior=PermissionBehavior.ALLOW)


async def prepare_schedule_scope(
    storage: StorageBase,
    user_id: str,
    agent_id: str,
    session_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Register a scheduled run's immutable project scope before agent assembly."""
    session = await storage.get_session(user_id, agent_id, session_id)
    if session is None:
        raise RuntimeError("Scheduled session is unavailable")
    if session.source != SessionSource.SCHEDULE:
        return
    if not session.source_schedule_id or not settings.agent_internal_key:
        raise RuntimeError("Scheduled session scope is unavailable")

    async def bind(http: httpx.AsyncClient) -> None:
        response = await http.post(
            f"{settings.api_prefix}/internal/schedule-sessions",
            headers={"X-Agent-Internal-Key": settings.agent_internal_key},
            json={
                "user_id": user_id,
                "session_id": session_id,
                "schedule_id": session.source_schedule_id,
            },
        )
        response.raise_for_status()

    if client is not None:
        await bind(client)
    else:
        async with httpx.AsyncClient(
            base_url=settings.business_api_url.rstrip("/"),
            timeout=20.0,
        ) as http:
            await bind(http)


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

    async def discover_papers(query: str, limit: int = 8) -> dict:
        """Find external paper candidates; results have no registered citation IDs."""
        return await request(
            "POST",
            "discover-papers",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "query": query,
                "limit": max(1, min(limit, 10)),
            },
        )

    async def import_selected_papers() -> dict:
        """Start only the batch explicitly selected and approved in this session."""
        return await request(
            "POST",
            "import-approved",
            json={"user_id": user_id, "session_id": session_id},
        )

    return [
        PaperReadTool(func, is_read_only=True, is_concurrency_safe=True)
        for func in (list_papers, search_papers, get_paper_excerpt, discover_papers)
    ] + [
        ApprovedImportTool(
            import_selected_papers, is_read_only=False, is_concurrency_safe=False
        )
    ]
