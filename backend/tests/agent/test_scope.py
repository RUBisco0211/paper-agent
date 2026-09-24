"""AgentScope 运行器的事件映射（离线：用假 Agent，不调模型）。"""

from collections.abc import AsyncIterator
from uuid import uuid4

from agentscope import event as E
from agentscope.message import Msg, TextBlock, ThinkingBlock, Usage

from app.agent.scope import AgentScopeRunner, _build_model
from app.agent.tools import SessionToolContext, SessionTools, ToolServices
from app.retrieval.domain import (
    ChannelReport,
    ChannelStatus,
    Evidence,
    SearchOutcome,
    SearchStatus,
)
from app.sessions.domain import Citation
from app.sessions.ports import AgentEventType, AgentTurnRequest, LlmConfig


class _FakeSession:
    """工具会把 Session 当上下文管理器使用。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeLibrary:
    def __init__(self, entries=None) -> None:
        self.entries = entries or []

    def list_entries(self, *, user_id, limit, offset, query=None):
        return self.entries, len(self.entries)

    def entries_for(self, *, user_id, user_paper_ids):
        return self.entries

    def get_entry(self, *, user_id, user_paper_id):
        return self.entries[0] if self.entries else None


class FakeSearch:
    def __init__(self, paper_id) -> None:
        self.paper_id = paper_id

    def search(self, *, user_id, query, scope, limit, project_id=None, paper_ids=None):
        return SearchOutcome(
            status=SearchStatus.DEGRADED,
            evidence=[
                Evidence(
                    paper_id=self.paper_id,
                    chunk_ids=[uuid4()],
                    title_path="3 Model",
                    snippet="scaled dot product attention",
                    page_start=2,
                    page_end=2,
                    score=0.4,
                    chunk_index=0,
                ),
            ],
            channels={"keyword": ChannelReport("keyword", ChannelStatus.OK, 1)},
        )


class FakeCitations:
    def __init__(self) -> None:
        self.registry: dict[str, Citation] = {}

    def record_evidence(self, *, session_id, evidence):
        recorded = []
        for index, item in enumerate(evidence):
            citation = Citation(
                citation_id=f"cit_{index:04d}",
                session_id=session_id,
                user_paper_id=item.paper_id,
                chunk_ids=list(item.chunk_ids),
                title_path=item.title_path,
                snippet=item.snippet,
                page_start=item.page_start,
                page_end=item.page_end,
            )
            self.registry[citation.citation_id] = citation
            recorded.append(citation)
        return recorded

    def get(self, *, user_id, session_id, citation_id):
        return self.registry[citation_id]


class FakeAgent:
    """按脚本产出 AgentScope 事件；可选先真实调用一次检索工具。"""

    def __init__(
        self,
        script,
        tools: SessionTools | None = None,
        call_tools: bool = False,
        capture: dict | None = None,
    ) -> None:
        self._script = script
        self._tools = tools
        self._call_tools = call_tools
        self._capture = capture

    def observe(self, msgs) -> None:
        if self._capture is not None:
            self._capture["observed"] = msgs if isinstance(msgs, list) else [msgs]

    async def reply_stream(
        self, inputs, *, yield_final_msg: bool = False
    ) -> AsyncIterator:
        if self._capture is not None:
            self._capture["inputs"] = [inputs]
        if self._call_tools and self._tools is not None:
            self._tools.search_papers("attention")
        for item in self._script:
            yield item


def _runner(script, *, call_tools: bool = False, capture: dict | None = None):
    paper_id = uuid4()
    citations = FakeCitations()
    library = FakeLibrary()

    def tools_factory(context: SessionToolContext) -> SessionTools:
        return SessionTools(
            context,
            ToolServices(
                session_factory=_FakeSession,
                library_factory=lambda session: library,
                search_factory=lambda session: FakeSearch(paper_id),
                citation_factory=lambda session: citations,
            ),
        )

    def agent_factory(request, context, toolkit, tools):
        return FakeAgent(
            script(context, tools),
            tools=tools,
            call_tools=call_tools,
            capture=capture,
        )

    runner = AgentScopeRunner(
        session_factory=lambda: None,
        agent_factory=agent_factory,
        tools_factory=tools_factory,
        timeout_seconds=5,
    )
    return runner, paper_id


def _request(**scope) -> AgentTurnRequest:
    return AgentTurnRequest(
        session_id=uuid4(),
        user_id=uuid4(),
        scope={"kind": "library", **scope},
        messages=[
            {"role": "system", "content": "范围提示"},
            {"role": "user", "content": "第一篇讲了什么？"},
        ],
        llm_config=LlmConfig(provider="openai", model="gpt-test", api_key="sk-test"),
    )


async def _collect(runner, request) -> list:
    return [event async for event in runner.stream(request)]


async def test_maps_text_tool_and_completion_events() -> None:
    tool_output = (
        '{"items":['
        + ",".join(f'{{"index":{index}}}' for index in range(300))
        + "]}"
    )

    def script(context, tools):
        return [
            E.ThinkingBlockDeltaEvent(
                reply_id="r", block_id="thinking", delta="先检索相关段落。"
            ),
            E.TextBlockDeltaEvent(reply_id="r", block_id="b", delta="这篇论文"),
            E.TextBlockDeltaEvent(
                reply_id="r", block_id="b", delta="提出了注意力机制。"
            ),
            E.ToolCallStartEvent(
                reply_id="r", tool_call_id="t1", tool_call_name="search_papers"
            ),
            E.ToolResultTextDeltaEvent(
                reply_id="r", tool_call_id="t1", delta=tool_output
            ),
            E.ToolResultEndEvent(reply_id="r", tool_call_id="t1", state="success"),
            E.ModelCallEndEvent(reply_id="r", input_tokens=120, output_tokens=45),
            E.ReplyEndEvent(session_id="s", reply_id="r", finished_reason="completed"),
        ]

    runner, _ = _runner(script, call_tools=True)
    events = await _collect(runner, _request())

    kinds = [event.type for event in events]
    assert kinds == [
        AgentEventType.THINKING_DELTA,
        AgentEventType.DELTA,
        AgentEventType.DELTA,
        AgentEventType.TRACE_MESSAGE,
        AgentEventType.TOOL_STARTED,
        AgentEventType.TOOL_COMPLETED,
        AgentEventType.COMPLETED,
    ]
    assert (
        "".join(
            event.data["text"] for event in events if event.type is AgentEventType.DELTA
        )
        == "这篇论文提出了注意力机制。"
    )
    assert events[0].data["text"] == "先检索相关段落。"
    assert events[4].data["tool"] == "search_papers"
    assert events[5].data["tool"] == "search_papers"
    assert events[5].data["content"] == tool_output

    completed = events[-1].data
    assert completed["usage"] == {"input_tokens": 120, "output_tokens": 45}
    # 工具登记过的引用会交给执行器写进 Assistant Entry
    assert completed["citations"] == ["cit_0000"]
    assert completed["tool_calls"] == ["search_papers"]


async def test_falls_back_to_the_final_message_when_no_deltas() -> None:
    def script(context, tools):
        return [
            Msg(
                name="assistant",
                role="assistant",
                content=[TextBlock(type="text", text="最终回答")],
                usage=Usage(input_tokens=10, output_tokens=5),
            ),
        ]

    runner, _ = _runner(script)
    events = await _collect(runner, _request())

    assert [event.type for event in events] == [
        AgentEventType.DELTA,
        AgentEventType.COMPLETED,
    ]
    assert events[0].data["text"] == "最终回答"
    assert events[1].data["usage"] == {"input_tokens": 10, "output_tokens": 5}


async def test_falls_back_to_thinking_in_the_final_message() -> None:
    def script(context, tools):
        return [
            Msg(
                name="assistant",
                role="assistant",
                content=[
                    ThinkingBlock(thinking="先核对原文。"),
                    TextBlock(text="最终回答"),
                ],
            ),
        ]

    runner, _ = _runner(script)
    events = await _collect(runner, _request())

    assert [event.type for event in events] == [
        AgentEventType.THINKING_DELTA,
        AgentEventType.DELTA,
        AgentEventType.COMPLETED,
    ]
    assert events[0].data["text"] == "先核对原文。"


async def test_final_message_fallback_survives_a_promoted_tool_plan() -> None:
    def script(context, tools):
        return [
            E.TextBlockDeltaEvent(reply_id="r", block_id="plan", delta="先检索。"),
            E.ToolCallStartEvent(
                reply_id="r",
                tool_call_id="t1",
                tool_call_name="search_papers",
            ),
            Msg(
                name="assistant",
                role="assistant",
                content=[TextBlock(text="最终回答")],
            ),
        ]

    runner, _ = _runner(script)
    events = await _collect(runner, _request())

    assert [event.type for event in events] == [
        AgentEventType.DELTA,
        AgentEventType.TRACE_MESSAGE,
        AgentEventType.TOOL_STARTED,
        AgentEventType.DELTA,
        AgentEventType.COMPLETED,
    ]
    assert events[3].data["text"] == "最终回答"


async def test_max_iters_is_reported_as_a_stable_failure() -> None:
    def script(context, tools):
        return [E.ExceedMaxItersEvent(reply_id="r", name="agent")]

    runner, _ = _runner(script)
    events = await _collect(runner, _request())

    assert events[-1].type is AgentEventType.FAILED
    assert events[-1].data["code"] == "agent_max_iters"


async def test_provider_errors_are_classified() -> None:
    class Unauthorized(Exception):
        status_code = 401

    def script(context, tools):
        raise Unauthorized("invalid api key")

    runner, _ = _runner(script)
    events = await _collect(runner, _request())

    assert events[-1].type is AgentEventType.FAILED
    assert events[-1].data["code"] == "llm_not_configured"


async def test_missing_user_message_fails_before_calling_the_model() -> None:
    def script(context, tools):
        return []

    runner, _ = _runner(script)
    request = _request()
    request = AgentTurnRequest(
        session_id=request.session_id,
        user_id=request.user_id,
        scope=request.scope,
        messages=[{"role": "system", "content": "只有系统提示"}],
        llm_config=request.llm_config,
    )

    events = await _collect(runner, request)

    assert [event.type for event in events] == [AgentEventType.FAILED]
    assert events[0].data["code"] == "validation_error"


async def test_history_is_observed_and_only_the_last_user_message_is_sent() -> None:
    def script(context, tools):
        return [
            E.ReplyEndEvent(session_id="s", reply_id="r", finished_reason="completed")
        ]

    capture: dict = {}
    runner, _ = _runner(script, capture=capture)
    project_id = uuid4()
    request = AgentTurnRequest(
        session_id=uuid4(),
        user_id=uuid4(),
        scope={"kind": "project", "project_id": str(project_id)},
        messages=[
            {"role": "system", "content": "范围"},
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "第一答"},
            {"role": "tool", "name": "search_papers", "content": "工具结果"},
            {"role": "user", "content": "第二问"},
        ],
        llm_config=LlmConfig(provider="openai", model="m", api_key="k"),
    )

    await _collect(runner, request)

    # 历史只保留 user/assistant，工具结果不进模型历史（Entry 里已有）
    assert [message.content[0].text for message in capture["observed"]] == [
        "第一问",
        "第一答",
    ]
    assert capture["inputs"][0].content[0].text == "第二问"
    assert [message.content[0].text for message in capture["inputs"]] == ["第二问"]


def test_builds_agentscope_native_models_for_enabled_providers() -> None:
    expected = {
        "anthropic": "AnthropicChatModel",
        "dashscope": "DashScopeChatModel",
        "deepseek": "DeepSeekChatModel",
        "moonshot": "MoonshotChatModel",
        "openai": "OpenAIChatModel",
        "xai": "XAIChatModel",
    }

    for provider, class_name in expected.items():
        model = _build_model(
            LlmConfig(provider=provider, model="test-model", api_key="test-key")
        )
        assert type(model).__name__ == class_name


def test_passes_supported_reasoning_effort_to_model_parameters() -> None:
    model = _build_model(
        LlmConfig(
            provider="openai",
            model="gpt-5.6-luna",
            api_key="test-key",
            reasoning_effort="high",
        )
    )

    assert model.parameters.reasoning_effort == "high"
