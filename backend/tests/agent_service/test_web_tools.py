"""The agent's web tools read through the business service and report failures
as stable codes instead of raising.
"""

import asyncio
import json
from uuid import uuid4

from agentscope.tool import Toolkit

from agent_service.paper_agent import PaperAgent
from agent_service.tools import build_agent_tools

USER_ID = str(uuid4())
SESSION_ID = str(uuid4())


def _tool(name: str):
    tools = asyncio.run(build_agent_tools(USER_ID, "agent", SESSION_ID))
    return next(item for item in tools if item.name == name)


def test_paper_agent_exposes_the_web_tools_alongside_the_library_tools():
    tools = asyncio.run(build_agent_tools(USER_ID, "agent", SESSION_ID))
    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=Toolkit(tools=tools),
    )
    schemas = asyncio.run(agent.toolkit.get_tool_schemas())
    names = {schema["function"]["name"] for schema in schemas}
    assert {"web_search", "web_fetch", "web_extract_excerpt"} <= names


def test_web_fetch_asks_the_business_service_for_a_window_of_the_page(monkeypatch):
    seen: dict = {}

    async def fake_request(method, path, **kwargs):
        seen.update(method=method, path=path, json=kwargs.get("json"))
        return {"status": "ok", "content": "body"}

    monkeypatch.setattr("agent_service.tools.web.business_request", fake_request)
    result = asyncio.run(_tool("web_fetch")(url="https://example.org/a", offset=8000))

    assert json.loads(result.content[0].text) == {"status": "ok", "content": "body"}
    assert seen["path"] == "web-fetch"
    assert seen["json"]["offset"] == 8000
    assert seen["json"]["user_id"] == USER_ID


def test_excerpt_reads_ask_for_passages_chosen_by_the_question(monkeypatch):
    seen: dict = {}

    async def fake_request(method, path, **kwargs):
        seen.update(json=kwargs.get("json"))
        return {"status": "ok", "excerpt_only": True}

    monkeypatch.setattr("agent_service.tools.web.business_request", fake_request)
    asyncio.run(
        _tool("web_extract_excerpt")(
            url="https://example.org/a", query="what is RSC", chunks=4
        )
    )

    assert seen["json"]["chunks"] == 4
    assert seen["json"]["query"] == "what is RSC"
