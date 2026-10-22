import asyncio
from uuid import uuid4

from agentscope.permission import PermissionBehavior

from agent_service.tools import build_agent_tools


def test_agent_tools_expose_project_capabilities_when_built() -> None:
    tools = asyncio.run(build_agent_tools(str(uuid4()), "agent", str(uuid4())))

    assert {tool.name for tool in tools} == {
        "list_papers",
        "search_papers",
        "get_paper_excerpt",
        "web_search",
        "web_fetch",
        "web_extract_excerpt",
        "discover_papers",
        "import_selected_papers",
        "ask_user",
        "create_scheduled_task",
    }
    assert sum(not tool.is_read_only for tool in tools) == 3
    assert all("scope" not in str(tool.input_schema) for tool in tools)


def test_approved_import_tool_allows_execution_when_user_setting_permits_it() -> None:
    tools = asyncio.run(
        build_agent_tools(
            str(uuid4()),
            "agent",
            str(uuid4()),
            always_allow={"import_selected_papers": True},
        )
    )
    importer = next(tool for tool in tools if tool.name == "import_selected_papers")
    decision = asyncio.run(importer.check_permissions({}, None))
    assert decision.behavior is PermissionBehavior.ALLOW
