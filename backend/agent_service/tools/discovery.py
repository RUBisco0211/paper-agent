"""External scholarly discovery and pre-approved imports."""

from agentscope.tool import ToolBase

from .base import ApprovedImportTool, PaperReadTool
from .request import business_request


def build_discovery_tools(
    user_id: str, session_id: str, *, always_allow_import: bool = False
) -> list[ToolBase]:
    async def discover_papers(query: str, limit: int = 8) -> dict:
        """Find external paper candidates; results have no registered citation IDs."""
        return await business_request(
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
        return await business_request(
            "POST",
            "import-approved",
            json={"user_id": user_id, "session_id": session_id},
        )

    return [
        PaperReadTool(discover_papers, is_read_only=True, is_concurrency_safe=True),
        ApprovedImportTool(
            import_selected_papers,
            is_read_only=False,
            is_concurrency_safe=False,
            always_allow=always_allow_import,
        ),
    ]
