from typing import Protocol
from uuid import UUID


class ProjectSessionGuard(Protocol):
    """Check for AgentScope bindings before a project is deleted."""

    def has_project_sessions(self, *, user_id: UUID, project_id: UUID) -> bool: ...
