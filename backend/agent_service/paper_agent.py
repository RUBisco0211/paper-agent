"""AgentScope agent limited to the project's session-bound tool groups."""

from agentscope.agent import Agent
from agentscope.permission import PermissionBehavior, PermissionRule
from agentscope.tool import ToolGroup, Toolkit

from .tools.base import (
    ApprovedImportTool,
    AskUserTool,
    PaperReadTool,
    ScheduleCreateTool,
)

LIBRARY_TOOLS = frozenset({"list_papers", "search_papers"})
WEB_TOOLS = frozenset({"web_search", "web_fetch", "web_extract_excerpt"})
DISCOVERY_TOOLS = frozenset({"discover_papers", "import_selected_papers"})
INTERACTION_TOOLS = frozenset({"ask_user"})
SCHEDULE_TOOLS = frozenset({"create_scheduled_task"})
PROJECT_TOOL_NAMES = (
    LIBRARY_TOOLS | WEB_TOOLS | DISCOVERY_TOOLS | INTERACTION_TOOLS | SCHEDULE_TOOLS
)


class FixedProjectToolkit(Toolkit):
    """Keep named groups for organization while exposing a stable tool schema."""

    async def _get_available_tools(self, groups=None):
        available = await super()._get_available_tools(
            [group.name for group in self.tool_groups]
        )
        available.pop("reset_tools", None)
        return available

    async def check_tool_available(self, tool_name, activated_groups):
        return await super().check_tool_available(
            tool_name, [group.name for group in self.tool_groups]
        )


class PaperAgent(Agent):
    def __init__(self, *args, toolkit: Toolkit | None = None, **kwargs) -> None:
        groups = toolkit.tool_groups if toolkit is not None else []
        allowed = {}
        for group in groups:
            for tool in group.tools:
                if (
                    (
                        isinstance(tool, PaperReadTool)
                        and tool.name in LIBRARY_TOOLS | WEB_TOOLS | {"discover_papers"}
                    )
                    or (
                        isinstance(tool, ApprovedImportTool)
                        and tool.name == "import_selected_papers"
                    )
                    or (isinstance(tool, AskUserTool) and tool.name == "ask_user")
                    or (
                        isinstance(tool, ScheduleCreateTool)
                        and tool.name == "create_scheduled_task"
                    )
                ):
                    if tool.name in allowed:
                        raise RuntimeError("Duplicate project agent tool")
                    allowed[tool.name] = tool
        if set(allowed) != PROJECT_TOOL_NAMES:
            raise RuntimeError("Session-bound project tools are unavailable")
        approved = FixedProjectToolkit(
            tools=[allowed[name] for name in sorted(LIBRARY_TOOLS)],
            tool_groups=[
                ToolGroup(
                    name="public_web",
                    description=(
                        "Look things up on the public web to supply context the "
                        "library cannot."
                    ),
                    tools=[allowed[name] for name in sorted(WEB_TOOLS)],
                ),
                ToolGroup(
                    name="paper_discovery",
                    description="Find papers and import a user-approved selection.",
                    tools=[allowed[name] for name in sorted(DISCOVERY_TOOLS)],
                ),
                ToolGroup(
                    name="user_questions",
                    description="Ask the current user for missing information.",
                    tools=[allowed[name] for name in sorted(INTERACTION_TOOLS)],
                ),
                ToolGroup(
                    name="system_functions",
                    description="Create a weekly task at the user's request.",
                    tools=[allowed[name] for name in sorted(SCHEDULE_TOOLS)],
                ),
            ],
        )
        super().__init__(*args, toolkit=approved, **kwargs)
        for name in {"import_selected_papers", "create_scheduled_task"}:
            tool = allowed[name]
            if getattr(tool, "always_allow", False):
                self.state.permission_context.ask_rules.pop(name, None)
                continue
            self.state.permission_context.ask_rules[name] = [
                PermissionRule(
                    tool_name=name,
                    rule_content=None,
                    behavior=PermissionBehavior.ASK,
                    source="userSettings",
                )
            ]
