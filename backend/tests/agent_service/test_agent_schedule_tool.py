"""The agent receives only a bounded schedule creation tool."""

import asyncio
from uuid import uuid4

import httpx
import pytest


def test_schedule_tool_accepts_weekly_cadence_without_scope_or_cron_arguments():
    from agent_service.tools import build_agent_tools

    tools = asyncio.run(build_agent_tools(str(uuid4()), "agent", str(uuid4())))
    scheduled = next(tool for tool in tools if tool.name == "create_scheduled_task")
    parameters = scheduled.input_schema.get("parameters", scheduled.input_schema)
    names = set(parameters["properties"])
    assert {"name", "prompt", "time", "weekdays"} <= names
    assert not {
        "user_id", "project_id", "session_id", "cron_expression", "timezone"
    } & names
    assert "weekdays" not in parameters.get("required", [])


def test_schedule_tool_normalizes_clear_local_time_expressions():
    from agent_service.tools.schedules import normalize_schedule_time

    assert normalize_schedule_time("中午12:30") == "12:30"
    assert normalize_schedule_time("下午3点") == "15:00"
    assert normalize_schedule_time("下午3点半") == "15:30"
    with pytest.raises(ValueError):
        normalize_schedule_time("晚点")


def test_schedule_tool_defaults_to_daily_without_exposing_timezone(monkeypatch):
    from agent_service.tools import schedules

    submitted = []

    async def fake_request(method, path, **kwargs):
        submitted.append(kwargs["json"])
        return {"schedule_id": "created"}

    monkeypatch.setattr(schedules, "business_request", fake_request)
    tool = schedules.build_schedule_tool(str(uuid4()), "agent", str(uuid4()))
    result = asyncio.run(
        tool(name="问候", prompt="问好", time="中午12:30", weekdays=[])
    )
    assert result is not None
    assert submitted[0]["time"] == "12:30"
    assert submitted[0]["weekdays"] == [
        "mon", "tue", "wed", "thu", "fri", "sat", "sun"
    ]
    assert "timezone" not in submitted[0]


def test_schedule_tool_hides_internal_endpoint_on_failure(monkeypatch):
    from agent_service.tools import schedules

    async def failed_request(*_args, **_kwargs):
        request = httpx.Request(
            "POST", "http://localhost/v1/internal/agent-schedules"
        )
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("404", request=request, response=response)

    monkeypatch.setattr(schedules, "business_request", failed_request)
    tool = schedules.build_schedule_tool(str(uuid4()), "agent", str(uuid4()))
    with pytest.raises(RuntimeError, match="定时任务创建失败") as error:
        asyncio.run(tool(name="问候", prompt="问好", time="12:30"))
    assert "internal" not in str(error.value)
