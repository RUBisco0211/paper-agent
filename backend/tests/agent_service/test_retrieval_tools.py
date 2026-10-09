import asyncio
from uuid import uuid4

from agentscope.permission import PermissionBehavior

from agent_service.retrieval_tools import build_retrieval_tools


def test_agent_tools_expose_four_reads_import_and_ask_user_when_built() -> None:
    tools = asyncio.run(build_retrieval_tools(str(uuid4()), "agent", str(uuid4())))

    assert {tool.name for tool in tools} == {
        "list_papers",
        "search_papers",
        "get_paper_excerpt",
        "discover_papers",
        "import_selected_papers",
        "ask_user",
    }
    assert sum(not tool.is_read_only for tool in tools) == 2
    assert all("scope" not in str(tool.input_schema) for tool in tools)


def test_approved_import_tool_allows_execution_after_server_side_approval() -> None:
    tools = asyncio.run(build_retrieval_tools(str(uuid4()), "agent", str(uuid4())))
    importer = next(tool for tool in tools if tool.name == "import_selected_papers")
    decision = asyncio.run(importer.check_permissions({}, None))
    assert decision.behavior is PermissionBehavior.ALLOW
