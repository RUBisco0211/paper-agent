"""Explicit failure adapter for executors without a configured runner."""

from collections.abc import AsyncIterator

from ..platform.errors import ErrorCode
from ..sessions.ports import AgentEvent, AgentEventType, AgentRunner, AgentTurnRequest


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
