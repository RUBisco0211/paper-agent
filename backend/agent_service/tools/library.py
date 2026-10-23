"""Read-only tools for the bound paper library."""

from agentscope.tool import ToolBase

from .base import PaperReadTool
from .request import business_request


def build_library_tools(user_id: str, session_id: str) -> list[ToolBase]:
    async def list_papers(limit: int = 20, offset: int = 0) -> dict:
        """List papers in this session's authorized library or project scope."""
        return await business_request(
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
        return await business_request(
            "POST",
            "search",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "query": query,
                "limit": max(1, min(limit, 20)),
            },
        )

    return [
        PaperReadTool(func, is_read_only=True, is_concurrency_safe=True)
        for func in (list_papers, search_papers)
    ]
