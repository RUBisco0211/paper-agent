"""AgentScope agent limited to session-bound paper retrieval."""

from agentscope.agent import Agent
from agentscope.tool import Toolkit

from .retrieval_tools import PaperReadTool


PAPER_TOOL_NAMES = frozenset(
    {"list_papers", "search_papers", "get_paper_excerpt"},
)


class PaperAgent(Agent):
    def __init__(self, *args, toolkit: Toolkit | None = None, **kwargs) -> None:
        groups = toolkit.tool_groups if toolkit is not None else []
        allowed = [
            tool
            for group in groups
            for tool in group.tools
            if isinstance(tool, PaperReadTool) and tool.name in PAPER_TOOL_NAMES
        ]
        if {tool.name for tool in allowed} != PAPER_TOOL_NAMES:
            raise RuntimeError("Session-bound paper tools are unavailable")
        super().__init__(*args, toolkit=Toolkit(tools=allowed), **kwargs)
