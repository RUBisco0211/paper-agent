"""External scheduling remains owned by AgentScope."""

from typing import Protocol


class AgentScheduleGateway(Protocol):
    def create_disabled(
        self,
        *,
        user_id: str,
        agent_id: str,
        session_id: str,
        name: str,
        prompt: str,
        cron_expression: str,
        timezone: str,
    ) -> str: ...

    def enable(self, *, user_id: str, schedule_id: str) -> None: ...

    def delete(self, *, user_id: str, schedule_id: str) -> None: ...
