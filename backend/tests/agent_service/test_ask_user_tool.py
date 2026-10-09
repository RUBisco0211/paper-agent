import asyncio
from uuid import uuid4

from agentscope.tool import Toolkit

from agent_service.paper_agent import PaperAgent
from agent_service.retrieval_tools import build_retrieval_tools


def test_paper_agent_exposes_an_external_ask_user_tool_for_questionnaires() -> None:
    tools = asyncio.run(build_retrieval_tools(str(uuid4()), "agent", str(uuid4())))
    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=Toolkit(tools=tools),
    )

    tool = next(
        tool
        for group in agent.toolkit.tool_groups
        for tool in group.tools
        if tool.name == "ask_user"
    )
    assert tool.is_external_tool is True
    assert tool.is_concurrency_safe is False
