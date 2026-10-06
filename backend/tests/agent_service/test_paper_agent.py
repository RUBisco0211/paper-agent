import asyncio
from uuid import uuid4

from agentscope.tool import FunctionTool, Toolkit

from agent_service.paper_agent import PaperAgent
from agent_service.retrieval_tools import build_retrieval_tools


def test_paper_agent_exposes_only_session_bound_read_tools_when_framework_adds_defaults() -> None:
    read_tools = asyncio.run(
        build_retrieval_tools(str(uuid4()), "agent", str(uuid4())),
    )

    def write_file(path: str) -> str:
        return path

    toolkit = Toolkit(tools=[FunctionTool(write_file), *read_tools])
    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=toolkit,
    )

    assert {
        tool.name
        for group in agent.toolkit.tool_groups
        for tool in group.tools
    } == {"list_papers", "search_papers", "get_paper_excerpt"}
    assert all(not group.mcps and not group.skills_or_loaders for group in agent.toolkit.tool_groups)
