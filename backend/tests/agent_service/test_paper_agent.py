import asyncio
from uuid import uuid4

from agentscope.message import TextBlock
from agentscope.tool import FunctionTool, ToolChunk, Toolkit

from agent_service.paper_agent import PaperAgent
from agent_service.tools import build_agent_tools


def test_paper_agent_exposes_bound_read_tools_when_defaults_exist() -> None:
    read_tools = asyncio.run(
        build_agent_tools(str(uuid4()), "agent", str(uuid4())),
    )

    def write_file(path: str) -> ToolChunk:
        return ToolChunk(content=[TextBlock(text=path)])

    toolkit = Toolkit(tools=[FunctionTool(write_file), *read_tools])
    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=toolkit,
    )

    assert {
        tool.name for group in agent.toolkit.tool_groups for tool in group.tools
    } == {
        "list_papers",
        "search_papers",
        "web_search",
        "web_fetch",
        "web_extract_excerpt",
        "discover_papers",
        "import_selected_papers",
        "ask_user",
        "create_scheduled_task",
    }
    assert all(
        not group.mcps and not group.skills_or_loaders
        for group in agent.toolkit.tool_groups
    )
