"""AgentScope agent limited to the project's session-bound tool groups."""

from agentscope.agent import Agent
from agentscope.permission import PermissionBehavior, PermissionRule
from agentscope.tool import ToolGroup, Toolkit

from .tools.base import (
    ApprovedImportTool,
    AskUserTool,
    PaperImageTool,
    PaperReadTool,
    ScheduleCreateTool,
)

LIBRARY_TOOLS = frozenset(
    {"list_papers", "search_papers", "read_paper", "read_paper_image"}
)
WEB_TOOLS = frozenset({"web_search", "web_fetch", "web_extract_excerpt"})
DISCOVERY_TOOLS = frozenset({"discover_papers", "import_selected_papers"})
INTERACTION_TOOLS = frozenset({"ask_user"})
SCHEDULE_TOOLS = frozenset({"create_scheduled_task"})
PROJECT_TOOL_NAMES = (
    LIBRARY_TOOLS | WEB_TOOLS | DISCOVERY_TOOLS | INTERACTION_TOOLS | SCHEDULE_TOOLS
)

#: Appended to the stored system prompt so reading stays search-first.
READING_GUIDANCE = """

## Reading the library
- Locate evidence with `search_papers` first. Only its results carry citation IDs.
- Use `read_paper` only when a search misses the answer, when you need
  continuous context around an excerpt, or when the user names a paper or page.
- Text from `read_paper` is for understanding. It is not citable: never cite it
  and never invent a citation ID for it. Cite only evidence from `search_papers`.
- Figures appear in page text as `[图片 | block N | 第P页]`. Read one with
  `read_paper_image(paper_id, block_id)`; when the current model cannot view
  images you receive the caption and page only, so say so instead of guessing
  what the picture shows.
- Answer in the language the user writes in.
"""


def _model_supports_images(model: object) -> bool:
    """Read the media types the current model's formatter forwards."""
    formatter = getattr(model, "formatter", None)
    media_types = getattr(formatter, "supported_input_media_types", None) or []
    return any(str(item).startswith("image/") for item in media_types)


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
        # The app runtime always supplies a workspace as offloader. This
        # product has no file access: keep built-in compression/truncation,
        # but neither offload content nor inject workspace directory prompts.
        kwargs["offloader"] = None
        if kwargs.get("system_prompt"):
            kwargs["system_prompt"] += READING_GUIDANCE
        supports_images = _model_supports_images(kwargs.get("model"))
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
        for tool in allowed.values():
            if isinstance(tool, PaperImageTool):
                tool.supports_images = supports_images
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
