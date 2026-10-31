"""Scheduled notifications follow persisted terminal replies, not tools."""

import asyncio

from agentscope.message import Msg, TextBlock, ThinkingBlock, ToolCallBlock
from agentscope.types import ErrorInfo, ErrorType, ReplyFinishedReason


def test_schedule_result_excludes_intermediate_content_when_tools_precede_answer():
    from agent_service.schedule_notifications import result_payload

    msg = Msg(
        name="reader",
        role="assistant",
        content=[
            TextBlock(text="intermediate"),
            ToolCallBlock(id="call", name="search", input="{}"),
            ThinkingBlock(thinking="private reasoning"),
            TextBlock(text="# Final\n\n" + "complete answer " * 1000),
            TextBlock(text="Second paragraph"),
        ],
        finished_reason=ReplyFinishedReason.COMPLETED,
    )
    result = result_payload(msg)
    assert result == {
        "status": "success",
        "markdown": "# Final\n\n" + "complete answer " * 1000 + "\nSecond paragraph",
        "error": None,
    }


def test_schedule_result_excludes_partial_answer_when_run_failed():
    from agent_service.schedule_notifications import result_payload

    msg = Msg(
        name="reader",
        role="assistant",
        content=[TextBlock(text="partial secret")],
        finished_reason=ReplyFinishedReason.ERROR,
        error=ErrorInfo(
            type=ErrorType.RATE_LIMIT, message="sensitive upstream message"
        ),
    )
    result = result_payload(msg)
    assert result is not None
    assert result["status"] == "failed"
    assert result["markdown"] == ""
    assert "稍后" in result["error"]
    assert "sensitive" not in result["error"]


def test_schedule_tool_forwards_email_choice_when_user_requests_notifications(
    monkeypatch,
):
    from agent_service.tools import schedules

    sent = []

    async def request(*args, **kwargs):
        sent.append(kwargs["json"])
        return {}

    monkeypatch.setattr(schedules, "business_request", request)
    tool = schedules.build_schedule_tool("user", "agent", "session")
    asyncio.run(tool(name="Review", prompt="Read", time="09:00", notify_email=True))
    assert sent[0]["notify_email"] is True
    schema = tool.input_schema.get("parameters", tool.input_schema)
    assert not {"email", "recipient"} & set(schema["properties"])


def test_schedule_result_ignores_unfinished_reply_when_waiting_for_confirmation():
    from agent_service.schedule_notifications import result_payload

    msg = Msg(name="reader", role="assistant", content=[TextBlock(text="Waiting")])
    assert result_payload(msg) is None


def test_schedule_tool_leaves_the_email_choice_to_the_saved_default(
    monkeypatch,
):
    from agentscope.permission import PermissionBehavior

    from agent_service.tools import schedules

    sent = []

    async def request(*args, **kwargs):
        sent.append(kwargs["json"])
        return {}

    monkeypatch.setattr(schedules, "business_request", request)
    tool = schedules.build_schedule_tool("user", "agent", "session")
    asyncio.run(tool(name="Review", prompt="Read", time="09:00"))
    # 用户没表态时不发这个字段，由后端的账号默认值决定。
    assert "notify_email" not in sent[0]
    assert asyncio.run(tool.check_permissions()).behavior == PermissionBehavior.ASK
