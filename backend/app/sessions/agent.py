"""Agent execution boundary and validated user model selection."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from ..platform.errors import ErrorCode, ValidationError
from .model_catalog import model_is_available, reasoning_effort_is_available


class AgentEventType(StrEnum):
    STARTED = "generation.started"
    DELTA = "message.delta"
    THINKING_DELTA = "thinking.delta"
    TRACE_MESSAGE = "trace.message"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    QUEUE_UPDATED = "queue.updated"
    COMPLETED = "generation.completed"
    ABORTED = "generation.aborted"
    FAILED = "generation.failed"


@dataclass(frozen=True, slots=True)
class LlmConfig:
    """Validated transient LLM configuration; never persisted or logged."""

    provider: str
    model: str
    api_key: str = field(repr=False)
    reasoning_effort: str | None = None


@dataclass(frozen=True, slots=True)
class AgentEvent:
    type: AgentEventType
    data: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentTurnRequest:
    session_id: UUID
    user_id: UUID
    scope: dict
    messages: list[dict]
    llm_config: LlmConfig


class AgentRunner:
    """Streams one assistant turn; implemented by the AgentScope adapter."""

    name = "base"

    def stream(self, request: AgentTurnRequest) -> AsyncIterator[AgentEvent]:
        raise NotImplementedError


class UnconfiguredAgentRunner(AgentRunner):
    """Fallback used only when an executor is constructed without a runner."""

    name = "unconfigured"

    async def stream(self, request: AgentTurnRequest) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(
            AgentEventType.FAILED,
            {
                "code": str(ErrorCode.AGENT_UNAVAILABLE),
                "message": "Agent 执行器尚未接入 AgentScope，本次没有生成回答",
            },
        )


def validate_llm_config(
    *,
    provider: str,
    model: str,
    api_key: str,
    reasoning_effort: str | None = None,
) -> LlmConfig:
    """Accept only a provider/model pair published by the model catalog."""
    provider = provider.strip().lower()
    model = model.strip()
    api_key = api_key.strip()
    if not model_is_available(provider, model):
        raise ValidationError("请选择支持的模型")
    if not api_key:
        raise ValidationError("缺少 API Key")
    if not reasoning_effort_is_available(provider, model, reasoning_effort):
        raise ValidationError("所选模型不支持该思考强度")
    return LlmConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        reasoning_effort=reasoning_effort,
    )
