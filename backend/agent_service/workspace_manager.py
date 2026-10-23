"""Session-isolated, capability-free workspace bindings required by AgentScope."""

import asyncio
import hashlib
from pathlib import Path

from agentscope.app.workspace_manager import IsolationPolicy, WorkspaceManagerBase
from agentscope.workspace import WorkspaceBase

from .workspace import NoCapabilityWorkspace


class NoCapabilityWorkspaceManager(WorkspaceManagerBase):
    """Keep framework identities/lifecycles without creating directories or tools."""

    def __init__(self, workdir_root: str) -> None:
        self._root = Path(workdir_root).resolve()
        self._live: dict[tuple[str, str, str, str], NoCapabilityWorkspace] = {}
        self._fallback_ids: dict[tuple[str, str, str], str] = {}
        self._lock = asyncio.Lock()
        super().__init__(isolation=IsolationPolicy.PER_SESSION)

    async def get_workspace(
        self, user_id: str, agent_id: str, session_id: str,
        workspace_id: str | None = None,
    ) -> WorkspaceBase:
        identity = (user_id, agent_id, session_id)
        async with self._lock:
            if workspace_id is None:
                workspace_id = self._fallback_ids.get(identity)
            if workspace_id is None:
                workspace_id = self.assign_workspace_id(
                    user_id=user_id, agent_id=agent_id, session_id=session_id,
                )
            self._fallback_ids[identity] = workspace_id
            key = (*identity, workspace_id)
            workspace = self._live.get(key)
            if workspace is None or not workspace.is_alive:
                directory = hashlib.sha256("\0".join(key).encode()).hexdigest()
                workspace = NoCapabilityWorkspace(
                    workspace_id=workspace_id, workdir=str(self._root / directory),
                )
                await workspace.initialize()
                self._live[key] = workspace
            return workspace

    async def create_workspace(
        self, user_id: str, agent_id: str, session_id: str,
    ) -> WorkspaceBase:
        return await self.get_workspace(user_id, agent_id, session_id)

    async def close(self, workspace_id: str) -> None:
        async with self._lock:
            for key in list(self._live):
                if key[-1] == workspace_id:
                    await self._live.pop(key).close()
            self._fallback_ids = {
                key: value for key, value in self._fallback_ids.items()
                if value != workspace_id
            }

    async def close_all(self) -> None:
        async with self._lock:
            for workspace in self._live.values():
                await workspace.close()
            self._live.clear()
            self._fallback_ids.clear()


__all__ = ["NoCapabilityWorkspaceManager"]
