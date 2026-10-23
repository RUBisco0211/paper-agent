"""Workspace wiring for the AgentScope service.

AgentScope requires one workspace per session. Paper Agent has no filesystem or
shell capability, so the manager hands out :class:`NoCapabilityWorkspace`
instead of ``LocalWorkspace``, which would describe a writable working
directory in the system prompt and offer Bash / Read / Write tools.
"""

from agentscope.app.workspace_manager import IsolationPolicy, WorkspaceManagerBase
from agentscope.workspace import WorkspaceBase

from .workspace import NoCapabilityWorkspace


class NoCapabilityWorkspaceManager(WorkspaceManagerBase):
    """Resolve every session to a workspace that grants nothing."""

    def __init__(self, workdir_root: str) -> None:
        self._root = workdir_root
        self._live: dict[str, NoCapabilityWorkspace] = {}
        super().__init__(isolation=IsolationPolicy.PER_SESSION)

    async def _resolve(
        self, agent_id: str, workspace_id: str | None
    ) -> NoCapabilityWorkspace:
        key = workspace_id or f"{agent_id}:workspace"
        workspace = self._live.get(key)
        if workspace is None:
            workspace = NoCapabilityWorkspace(
                workspace_id=workspace_id,
                workdir=f"{self._root}/{agent_id}",
            )
            self._live[key] = workspace
        return workspace

    async def get_workspace(
        self,
        user_id: str,
        agent_id: str,
        session_id: str,
        workspace_id: str | None = None,
    ) -> WorkspaceBase:
        del user_id, session_id
        return await self._resolve(agent_id, workspace_id)

    async def create_workspace(
        self, user_id: str, agent_id: str, session_id: str
    ) -> WorkspaceBase:
        del user_id, session_id
        return await self._resolve(agent_id, None)

    async def close(self, workspace_id: str) -> None:
        self._live.pop(workspace_id, None)

    async def close_all(self) -> None:
        self._live.clear()


__all__ = ["NoCapabilityWorkspaceManager"]
