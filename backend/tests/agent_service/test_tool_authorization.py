"""Write tools require a per-call decision while all approved tools stay visible."""

import asyncio
from uuid import uuid4

from agentscope.permission import PermissionBehavior, PermissionContext, PermissionMode
from agentscope.tool import Toolkit

from agent_service.paper_agent import PaperAgent
from agent_service.tools import build_agent_tools


def test_paper_agent_exposes_all_approved_tools_without_a_reset_tool():
    tools = asyncio.run(build_agent_tools(str(uuid4()), "agent", str(uuid4())))
    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=Toolkit(tools=tools),
    )

    schemas = asyncio.run(agent.toolkit.get_tool_schemas())
    assert {schema["function"]["name"] for schema in schemas} == {
        "list_papers",
        "search_papers",
        "read_paper",
        "read_paper_image",
        "web_search",
        "web_fetch",
        "web_extract_excerpt",
        "discover_papers",
        "import_selected_papers",
        "ask_user",
        "create_scheduled_task",
    }
    assert [group.name for group in agent.toolkit.tool_groups] == [
        "basic",
        "public_web",
        "paper_discovery",
        "user_questions",
        "system_functions",
    ]


def test_write_tools_request_user_confirmation_by_default():
    tools = asyncio.run(build_agent_tools(str(uuid4()), "agent", str(uuid4())))
    for name in ("import_selected_papers", "create_scheduled_task"):
        tool = next(item for item in tools if item.name == name)
        decision = asyncio.run(tool.check_permissions({}, PermissionContext()))
        assert decision.behavior is PermissionBehavior.ASK
        assert decision.bypass_immune


def test_write_tool_still_asks_in_bypass_mode_without_a_user_override():
    tools = asyncio.run(build_agent_tools(str(uuid4()), "agent", str(uuid4())))
    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=Toolkit(tools=tools),
    )
    agent.state.permission_context.mode = PermissionMode.BYPASS
    importer = next(tool for tool in tools if tool.name == "import_selected_papers")

    decision = asyncio.run(agent._engine.check_permission(importer, {}))
    assert decision.behavior is PermissionBehavior.ASK


def test_user_override_skips_write_review_for_only_its_named_tool():
    tools = asyncio.run(
        build_agent_tools(
            str(uuid4()),
            "agent",
            str(uuid4()),
            always_allow={"import_selected_papers": True},
        )
    )
    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=Toolkit(tools=tools),
    )
    importer = next(tool for tool in tools if tool.name == "import_selected_papers")
    scheduled = next(tool for tool in tools if tool.name == "create_scheduled_task")

    assert (
        asyncio.run(agent._engine.check_permission(importer, {})).behavior
        is PermissionBehavior.ALLOW
    )
    assert (
        asyncio.run(agent._engine.check_permission(scheduled, {})).behavior
        is PermissionBehavior.ASK
    )


def test_changed_user_setting_replaces_saved_session_ask_rule():
    original_tools = asyncio.run(build_agent_tools(str(uuid4()), "agent", str(uuid4())))
    original = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=Toolkit(tools=original_tools),
    )
    updated_tools = asyncio.run(
        build_agent_tools(
            str(uuid4()),
            "agent",
            str(uuid4()),
            always_allow={"import_selected_papers": True},
        )
    )
    restored = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=Toolkit(tools=updated_tools),
        state=original.state,
    )
    importer = next(
        tool for tool in updated_tools if tool.name == "import_selected_papers"
    )
    decision = asyncio.run(restored._engine.check_permission(importer, {}))
    assert decision.behavior is PermissionBehavior.ALLOW
