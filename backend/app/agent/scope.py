"""AgentScope 执行器：把框架事件映射成我们自己的 AgentEvent。

- Provider 与模型来自只读目录，用户只输入 Key；配置只驻留当前执行器内存
- 工具范围由会话上下文注入；模型只能通过三个只读工具接触文献
- 工具调用与使用的 Citation 会被记下来，交由执行器写入 Entry
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID

import structlog
from agentscope.agent import Agent, ModelConfig, ReActConfig
from agentscope.credential import CredentialFactory
from agentscope.message import Msg, TextBlock, ThinkingBlock
from agentscope.tool import FunctionTool, Toolkit

from ..platform.config import settings
from ..platform.database import SessionFactory
from ..platform.errors import ErrorCode
from ..sessions.domain import MessageRole
from ..sessions.ports import AgentEvent, AgentEventType, AgentTurnRequest, LlmConfig
from .tools import SessionToolContext, SessionTools, ToolServices

logger = structlog.get_logger(__name__)

MAX_HISTORY_MESSAGES = 30

SYSTEM_PROMPT = """你是 Paper Agent，一个只依据用户文献库回答问题的研究助手。

规则：
1. 只能通过提供的工具获取文献内容；不得凭记忆或通用知识编造论文结论。
2. 引用原文时必须使用 search_papers 返回的 citation_id（形如 cit_ab12cd34），
   并在句末用方括号标注。
3. 证据不足时明确说明「文献中没有足够证据」，不要用推测补足。
4. 检索状态为 degraded 或 unavailable 时，如实说明检索受限，
   不要解释成「论文里没有相关内容」。
5. 用简体中文回答，论文术语与原文保持一致。
6. 每轮需要调用工具时，先用一句简短文字说明当前要做什么；获得结果后如需继续调用，
   先用一句简短文字说明刚得到的信息和下一步。不要在这些进度消息中编造尚未取得的结果。
7. 数学表达式必须使用 LaTeX 分隔符：行内用 $...$；块级公式的 $$ 必须各自独占一行。"""

TOOL_DESCRIPTIONS = {
    "list_papers": "列出本次会话授权范围内的文献（条目 ID、标题、是否有可检索全文）。",
    "search_papers": "在授权范围内检索论文原文证据，返回可引用的片段与 citation_id。",
    "get_paper_excerpt": "按 citation_id 展开原文片段与页码，用于核对结论。",
}

AgentFactory = Callable[
    [AgentTurnRequest, SessionToolContext, Toolkit, SessionTools], Any
]
ToolsFactory = Callable[[SessionToolContext], SessionTools]


class AgentScopeRunner:
    """实现 ``AgentRunner``：一次回合流式产出事件。"""

    name = "agentscope"

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        agent_factory: AgentFactory | None = None,
        tools_factory: ToolsFactory | None = None,
        max_iters: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._agent_factory = agent_factory or _build_agent
        self._tools_factory = tools_factory
        self._max_iters = max_iters or settings.agent_max_iters
        self._timeout_seconds = timeout_seconds or settings.agent_turn_timeout_seconds

    async def stream(self, request: AgentTurnRequest) -> AsyncIterator[AgentEvent]:
        context = SessionToolContext(
            session_id=request.session_id,
            user_id=request.user_id,
            project_id=_uuid_or_none(request.scope.get("project_id")),
            paper_id=_uuid_or_none(request.scope.get("paper_id")),
        )
        usage: dict[str, int] = {}
        tool_names: dict[str, str] = {}
        tool_outputs: dict[str, str] = {}
        emitted_thinking = False
        text_since_tool: list[str] = []
        failure: str | None = None
        failure_message: str | None = None
        tools: SessionTools | None = None

        try:
            tools = (
                self._tools_factory(context)
                if self._tools_factory is not None
                else SessionTools(
                    context,
                    ToolServices(session_factory=self._session_factory),
                )
            )
            toolkit = await build_toolkit(tools)
            agent = self._agent_factory(request, context, toolkit, tools)

            history, last_user_message = _split_messages(request.messages)
            if last_user_message is None:
                yield AgentEvent(
                    AgentEventType.FAILED,
                    {
                        "code": str(ErrorCode.VALIDATION_ERROR),
                        "message": "本次回合没有用户消息",
                    },
                )
                return
            if history:
                agent.observe(history)

            async with asyncio.timeout(self._timeout_seconds):
                async for item in agent.reply_stream(
                    last_user_message, yield_final_msg=True
                ):
                    if isinstance(item, Msg):
                        # 流式增量缺失时（例如供应商不支持）用最终消息兜底
                        final_thinking = _thinking_of(item)
                        if final_thinking and not emitted_thinking:
                            emitted_thinking = True
                            yield AgentEvent(
                                AgentEventType.THINKING_DELTA,
                                {"text": final_thinking},
                            )
                        final_text = _text_of(item)
                        if final_text and not text_since_tool:
                            text_since_tool.append(final_text)
                            yield AgentEvent(AgentEventType.DELTA, {"text": final_text})
                        usage = usage or _usage_of(item)
                        continue

                    event_name = type(item).__name__
                    if event_name == "TextBlockDeltaEvent":
                        delta = getattr(item, "delta", "") or ""
                        text_since_tool.append(delta)
                        yield AgentEvent(
                            AgentEventType.DELTA,
                            {"text": delta},
                        )
                    elif event_name == "ThinkingBlockDeltaEvent":
                        emitted_thinking = True
                        yield AgentEvent(
                            AgentEventType.THINKING_DELTA,
                            {"text": getattr(item, "delta", "") or ""},
                        )
                    elif event_name == "ToolCallStartEvent":
                        if text_since_tool:
                            yield AgentEvent(
                                AgentEventType.TRACE_MESSAGE,
                                {"text": "".join(text_since_tool)},
                            )
                            text_since_tool.clear()
                        tool_call_id = str(getattr(item, "tool_call_id", ""))
                        tool_name = str(getattr(item, "tool_call_name", "") or "tool")
                        tool_names[tool_call_id] = tool_name
                        yield AgentEvent(
                            AgentEventType.TOOL_STARTED,
                            {"tool_call_id": tool_call_id, "tool": tool_name},
                        )
                    elif event_name == "ToolResultTextDeltaEvent":
                        tool_call_id = str(getattr(item, "tool_call_id", ""))
                        tool_outputs[tool_call_id] = tool_outputs.get(
                            tool_call_id, ""
                        ) + str(getattr(item, "delta", "") or "")
                    elif event_name == "ToolResultEndEvent":
                        tool_call_id = str(getattr(item, "tool_call_id", ""))
                        state = str(getattr(item, "state", "") or "")
                        yield AgentEvent(
                            AgentEventType.TOOL_COMPLETED,
                            {
                                "tool_call_id": tool_call_id,
                                "tool": tool_names.get(tool_call_id, "tool"),
                                "state": state,
                                "content": tool_outputs.get(tool_call_id, ""),
                            },
                        )
                    elif event_name == "ModelCallEndEvent":
                        usage = {
                            "input_tokens": int(getattr(item, "input_tokens", 0) or 0),
                            "output_tokens": int(
                                getattr(item, "output_tokens", 0) or 0
                            ),
                        }
                    elif event_name == "ExceedMaxItersEvent":
                        failure = str(ErrorCode.AGENT_MAX_ITERS)
                        failure_message = "工具调用轮次达到上限，本次回答未完成"
                    elif event_name == "ReplyEndEvent":
                        error = getattr(item, "error", None)
                        if error:
                            failure = _classify_failure(error)
                            failure_message = str(error)[:300]
        except TimeoutError:
            failure = str(ErrorCode.AGENT_TIMEOUT)
            failure_message = f"本次回答超过 {self._timeout_seconds:.0f} 秒未完成"
        except Exception as exc:  # 供应商错误、网络问题等
            logger.warning(
                "agent.turn.failed",
                session_id=str(request.session_id),
                error_type=type(exc).__name__,
            )
            failure = _classify_failure(exc)
            failure_message = str(exc)[:300]

        citations = tools.collected_citations if tools is not None else []
        if failure:
            yield AgentEvent(
                AgentEventType.FAILED,
                {
                    "code": failure,
                    "message": failure_message or "生成失败",
                    "citations": citations,
                },
            )
            return

        yield AgentEvent(
            AgentEventType.COMPLETED,
            {
                "usage": usage,
                "citations": citations,
                "tool_calls": sorted(set(tool_names.values())),
            },
        )


# --- 默认装配 ---------------------------------------------------------------
def _build_agent(
    request: AgentTurnRequest,
    context: SessionToolContext,
    toolkit: Toolkit,
    tools: SessionTools,
) -> Agent:
    model = _build_model(request.llm_config)
    return Agent(
        name="paper-agent",
        system_prompt=SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
        model_config=ModelConfig(max_retries=0),
        react_config=ReActConfig(max_iters=settings.agent_max_iters),
    )


def _build_model(config: LlmConfig):
    """Build one of AgentScope's native provider clients from server config."""
    credential_data: dict[str, str] = {
        "type": f"{config.provider}_credential",
    }
    credential_data["api_key"] = config.api_key

    credential = CredentialFactory.from_dict(credential_data)
    model_class = credential.get_chat_model_class()
    parameters = None
    if config.reasoning_effort is not None:
        parameters = model_class.Parameters(reasoning_effort=config.reasoning_effort)
    return model_class(
        credential=credential,
        model=config.model,
        parameters=parameters,
        stream=True,
    )


async def build_toolkit(tools: SessionTools) -> Toolkit:
    """AgentScope 的工具注册是异步接口，这里一次性注册三个只读工具。"""
    toolkit = Toolkit()
    await toolkit.add_tool(
        [
            FunctionTool(
                func=tools.list_papers,
                name="list_papers",
                description=TOOL_DESCRIPTIONS["list_papers"],
                is_read_only=True,
            ),
            FunctionTool(
                func=tools.search_papers,
                name="search_papers",
                description=TOOL_DESCRIPTIONS["search_papers"],
                is_read_only=True,
            ),
            FunctionTool(
                func=tools.get_paper_excerpt,
                name="get_paper_excerpt",
                description=TOOL_DESCRIPTIONS["get_paper_excerpt"],
                is_read_only=True,
            ),
        ],
    )
    return toolkit


# --- 辅助 -------------------------------------------------------------------
def _split_messages(messages: list[dict]) -> tuple[list[Msg], Msg | None]:
    """把投影好的消息拆成「历史」与「本次输入」。

    工具结果不进模型历史：它们已作为 Entry 留在会话里，模型需要时重新检索。
    """
    history: list[Msg] = []
    pending_user: Msg | None = None
    for message in messages[-MAX_HISTORY_MESSAGES:]:
        role = str(message.get("role", ""))
        content = str(message.get("content", "") or "").strip()
        if role == "system" or not content:
            continue
        if role == MessageRole.TOOL.value:
            continue
        if role == MessageRole.USER.value:
            if pending_user is not None:
                history.append(pending_user)
            pending_user = _text_message(MessageRole.USER.value, content)
        elif role == MessageRole.ASSISTANT.value:
            # 先落同轮的 user，保证历史顺序是 user → assistant
            if pending_user is not None:
                history.append(pending_user)
                pending_user = None
            history.append(_text_message(MessageRole.ASSISTANT.value, content))
    return history, pending_user


def _text_message(role: str, content: str) -> Msg:
    return Msg(name=role, role=role, content=[TextBlock(type="text", text=content)])


def _text_of(message: Msg) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(str(getattr(block, "text", "")))
    return "".join(parts)


def _thinking_of(message: Msg) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if isinstance(block, ThinkingBlock):
            parts.append(block.thinking)
    return "".join(parts)


def _usage_of(message: Msg) -> dict[str, int]:
    usage = getattr(message, "usage", None)
    if usage is None:
        return {}
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
    }


def _classify_failure(error: object) -> str:
    """把供应商错误归类成稳定错误码，便于前端区分提示。"""
    status = getattr(error, "status_code", None)
    text = str(error).lower()
    if status in {401, 403} or any(
        key in text
        for key in ("api key", "unauthorized", "invalid_api_key", "authentication")
    ):
        return str(ErrorCode.LLM_NOT_CONFIGURED)
    if (
        status == 429
        or "rate limit" in text
        or "quota" in text
        or "insufficient" in text
    ):
        return str(ErrorCode.PROVIDER_RATE_LIMITED)
    if "timeout" in text or "timed out" in text:
        return str(ErrorCode.AGENT_TIMEOUT)
    return str(ErrorCode.PROVIDER_UNAVAILABLE)


def _uuid_or_none(value: object) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None
