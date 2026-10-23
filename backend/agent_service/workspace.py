"""A workspace binding that grants nothing.

AgentScope requires a workspace for every session and, left to its defaults,
describes one in the system prompt ("you can read and write files here…") while
adding Bash / Read / Write to the toolkit. Paper Agent exposes no filesystem,
shell, skill or MCP capability, so this workspace reports none of them: no
instructions, no tools, no skills, no MCPs. The whitelist in ``PaperAgent`` is
still the second line of defence.
"""

from agentscope.workspace import WorkspaceBase


class NoCapabilityWorkspace(WorkspaceBase):
    """The minimum AgentScope needs, with every capability switched off."""

    def __init__(self, *, workdir: str, workspace_id: str | None = None) -> None:
        super().__init__(workspace_id=workspace_id)
        self.workdir = workdir
        self.instructions = ""

    async def initialize(self) -> None:
        self.is_alive = True

    async def get_instructions(self) -> str:
        return ""

    async def list_tools(self) -> list:
        return []

    async def list_skills(self) -> list:
        return []

    async def list_mcps(self) -> list:
        return []
