"""Project-provided agent capabilities, bound to one authenticated session."""

from uuid import UUID

from agentscope.tool import ToolBase

from .discovery import build_discovery_tools
from .library import build_library_tools
from .questions import build_question_tool
from .schedules import build_schedule_tool
from .scope import prepare_schedule_scope
from .web import build_web_tools


async def build_agent_tools(
    user_id: str,
    agent_id: str,
    session_id: str,
    *,
    always_allow: dict[str, bool] | None = None,
) -> list[ToolBase]:
    UUID(user_id)
    UUID(session_id)
    policy = always_allow or {}
    return [
        *build_library_tools(user_id, session_id),
        *build_web_tools(user_id),
        *build_discovery_tools(
            user_id,
            session_id,
            always_allow_import=policy.get("import_selected_papers", False),
        ),
        build_question_tool(),
        build_schedule_tool(
            user_id,
            agent_id,
            session_id,
            always_allow=policy.get("create_scheduled_task", False),
        ),
    ]


__all__ = ["build_agent_tools", "prepare_schedule_scope"]
