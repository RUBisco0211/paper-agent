"""The agent's web tools read through the business service and report failures
as stable codes instead of raising.
"""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from agentscope.tool import Toolkit

from agent_service.paper_agent import PaperAgent
from agent_service.tools import build_agent_tools
from agent_service.tools.request import BusinessRequestFailed

USER_ID = str(uuid4())
SESSION_ID = str(uuid4())


def _tool(name: str):
    tools = asyncio.run(build_agent_tools(USER_ID, "agent", SESSION_ID))
    return next(item for item in tools if item.name == name)


def _payload(result) -> dict:
    return json.loads(result.content[0].text)


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

    assert _payload(result) == {"status": "ok", "content": "body"}
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


def test_a_missing_key_becomes_a_result_the_agent_can_act_on(monkeypatch):
    async def fake_request(method, path, **kwargs):
        raise BusinessRequestFailed(
            409,
            {
                "code": "provider_not_configured",
                "message": "尚未配置该服务的访问密钥",
            },
        )

    monkeypatch.setattr("agent_service.tools.web.business_request", fake_request)
    payload = _payload(asyncio.run(_tool("web_search")(query="RSC")))

    assert payload["status"] == "error"
    assert payload["code"] == "provider_not_configured"
    assert payload["message"] == "尚未配置该服务的访问密钥"


def test_a_rate_limit_keeps_its_own_code(monkeypatch):
    async def fake_request(method, path, **kwargs):
        raise BusinessRequestFailed(
            429, {"code": "rate_limited", "message": "稍后重试"}
        )

    monkeypatch.setattr("agent_service.tools.web.business_request", fake_request)
    payload = _payload(asyncio.run(_tool("web_fetch")(url="https://example.org/a")))

    assert payload["code"] == "rate_limited"


def test_a_transport_failure_reports_the_web_as_unavailable(monkeypatch):
    async def fake_request(method, path, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("agent_service.tools.web.business_request", fake_request)
    payload = _payload(asyncio.run(_tool("web_search")(query="RSC")))

    assert payload["status"] == "error"
    assert payload["code"] == "provider_unavailable"


def test_a_declared_failure_does_not_escape_as_an_exception(monkeypatch):
    async def fake_request(method, path, **kwargs):
        raise RuntimeError("AGENT_INTERNAL_KEY is required for agent tools")

    monkeypatch.setattr("agent_service.tools.web.business_request", fake_request)
    payload = _payload(asyncio.run(_tool("web_search")(query="RSC")))

    assert payload["status"] == "error"
    assert "AGENT_INTERNAL_KEY" in payload["message"]


@pytest.mark.parametrize("tool", ["web_search", "web_fetch", "web_extract_excerpt"])
def test_every_web_tool_is_read_only_and_never_asks_for_confirmation(tool):
    built = _tool(tool)
    assert built.is_read_only is True
