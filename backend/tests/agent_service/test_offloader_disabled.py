"""Run real AgentScope compression and tool-result truncation without file IO."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agentscope.agent import ContextConfig
from agentscope.message import AssistantMsg, ToolCallBlock, ToolResultBlock, UserMsg
from agentscope.tool import Toolkit
from agentscope.workspace import LocalWorkspace

from agent_service.paper_agent import PaperAgent
from agent_service.tools import build_agent_tools
from agent_service.tools.base import PaperReadTool
from agent_service.workspace import NoCapabilityWorkspace
from agent_service.workspace_manager import NoCapabilityWorkspaceManager


class SummaryModel:
    context_size = 1000

    async def count_tokens(self, messages, tools=None):
        return len(str(messages))

    async def generate_structured_output(self, *, messages, structured_model):
        return SimpleNamespace(
            finished_reason="stop",
            content=dict.fromkeys(structured_model["properties"], "summary-sentinel"),
            usage=None,
        )


async def make_agent(workspace, long_tool=False):
    tools = await build_agent_tools(str(uuid4()), "agent", str(uuid4()))
    if long_tool:
        async def list_papers() -> str:
            """Return an oversized library result."""
            return "tool-output-sentinel " * 300

        tools = [tool for tool in tools if tool.name != "list_papers"]
        tools.append(PaperReadTool(list_papers, is_read_only=True))
    return PaperAgent(
        name="Reader", system_prompt="Use registered paper evidence.",
        model=SummaryModel(), toolkit=Toolkit(tools=tools), offloader=workspace,
        context_config=ContextConfig(tool_result_limit=50),
    )


def test_system_prompt_excludes_file_instructions_when_runtime_supplies_workspace(
    tmp_path,
):
    async def run():
        workspace = LocalWorkspace(workdir=str(tmp_path / "private-root"))
        agent = await make_agent(workspace)
        prompt = await agent._get_system_prompt()
        assert prompt.startswith("Use registered paper evidence.")
        assert "workspace" not in prompt.lower()
        assert "scratch/" not in prompt
        assert agent.offloader is None

    asyncio.run(run())


def test_builtin_compression_keeps_summary_when_runtime_supplies_no_backend(tmp_path):
    async def run():
        agent = await make_agent(NoCapabilityWorkspace(workdir=str(tmp_path)))
        agent.state.context = [UserMsg("user", "long-history " * 500)]
        await agent.compress_context()
        assert "summary-sentinel" in agent.state.summary
        assert "offloaded" not in agent.state.summary
        assert agent.offloader is None

    asyncio.run(run())


def test_long_tool_result_is_truncated_without_file_hint_when_offloading_is_disabled(
    tmp_path,
):
    async def run():
        agent = await make_agent(NoCapabilityWorkspace(workdir=str(tmp_path)), True)
        call = ToolCallBlock(id="call-1", name="list_papers", input="{}")
        agent.state.context = [AssistantMsg("Reader", [call])]
        events = [event async for event in agent._execute_tool_call(call)]
        assert events
        results = [block for msg in agent.state.context for block in msg.content
                   if isinstance(block, ToolResultBlock)]
        assert results
        output = str(results[-1].output)
        assert "TRUNCATED" in output
        assert "refer to the file" not in output
        assert agent.offloader is None

    asyncio.run(run())


def test_workspace_is_initialized_when_resolved_by_manager(tmp_path):
    async def run():
        manager = NoCapabilityWorkspaceManager(str(tmp_path))
        workspace = await manager.get_workspace("user", "agent", "session")
        assert workspace.is_alive

    asyncio.run(run())


@pytest.mark.parametrize(
    "other", [("other-user", "session"), ("user", "other-session")],
)
def test_workspace_is_distinct_when_owner_or_session_differs(tmp_path, other):
    async def run():
        manager = NoCapabilityWorkspaceManager(str(tmp_path))
        first = await manager.get_workspace("user", "agent", "session")
        second = await manager.get_workspace(other[0], "agent", other[1])
        assert first is not second
        assert first.workspace_id != second.workspace_id
        assert first.workdir != second.workdir

    asyncio.run(run())


@pytest.mark.parametrize("close_all", [False, True])
def test_workspace_is_closed_and_recreated_when_manager_releases_it(
    tmp_path, close_all,
):
    async def run():
        manager = NoCapabilityWorkspaceManager(str(tmp_path))
        workspace = await manager.get_workspace("user", "agent", "session", "saved-id")
        await workspace.initialize()
        if close_all:
            await manager.close_all()
        else:
            await manager.close(workspace.workspace_id)
        assert not workspace.is_alive
        renewed = await manager.get_workspace("user", "agent", "session", "saved-id")
        assert renewed is not workspace
        assert renewed.is_alive
        assert renewed.workspace_id == "saved-id"

    asyncio.run(run())
