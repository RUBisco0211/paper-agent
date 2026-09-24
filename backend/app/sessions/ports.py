"""Framework-independent agent execution contracts."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


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
