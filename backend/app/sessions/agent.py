"""Agent execution boundary for one session turn.

The first version deliberately ships a boundary plus an explicit "not wired yet"
runner: the session machinery (pending queues, entries, events, stop/resume) is
real, while actually running AgentScope is a separate change. The stub reports a
stable failure instead of pretending an answer was produced.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from ..platform.config import settings
from ..platform.errors import ErrorCode, ValidationError


class AgentEventType(StrEnum):
    STARTED = "generation.started"
    DELTA = "message.delta"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    QUEUE_UPDATED = "queue.updated"
    COMPLETED = "generation.completed"
    ABORTED = "generation.aborted"
    FAILED = "generation.failed"


@dataclass(frozen=True, slots=True)
class LlmConfig:
    """Transient LLM configuration; never persisted or logged."""

    provider: str
    model: str
    api_key: str = field(repr=False)

    @property
    def base_url(self) -> str:
        return settings.llm_providers[self.provider]


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
    """Explicit placeholder until AgentScope execution is wired in."""

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
    provider: str | None,
    model: str | None,
    api_key: str | None,
) -> LlmConfig:
    """Validate a transient LLM configuration against the provider allow-list."""
    if not provider or provider not in settings.llm_providers:
        raise ValidationError(
            "provider 不在允许列表中",
            details={"allowed": sorted(settings.llm_providers)},
        )
    if not model or not model.strip():
        raise ValidationError("缺少模型名称")
    if not api_key or not api_key.strip():
        raise ValidationError("缺少 API Key")
    return LlmConfig(provider=provider, model=model.strip(), api_key=api_key.strip())
