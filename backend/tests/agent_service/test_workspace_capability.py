"""Paper Agent has no filesystem, shell or skill surface at all."""

import asyncio
from pathlib import Path

from agent_service.main import create_agent_service_app
from agent_service.workspace import NoCapabilityWorkspace


def test_workspace_reports_no_instructions_so_the_prompt_never_describes_files(
    tmp_path: Path,
):
    workspace = NoCapabilityWorkspace(workspace_id="ws", workdir=str(tmp_path))

    assert workspace.instructions == ""
    assert asyncio.run(workspace.get_instructions()) == ""


def test_workspace_offers_no_tools_skills_or_mcps(tmp_path: Path):
    workspace = NoCapabilityWorkspace(workspace_id="ws", workdir=str(tmp_path))

    assert asyncio.run(workspace.list_tools()) == []
    assert asyncio.run(workspace.list_skills()) == []
    assert asyncio.run(workspace.list_mcps()) == []


def test_agent_service_resolves_sessions_to_the_capability_free_workspace(
    tmp_path: Path,
):
    app = create_agent_service_app("postgresql:///unused", tmp_path / "workspaces")
    manager = app.state.workspace_manager

    workspace = asyncio.run(manager.get_workspace("user", "agent", "session"))

    assert isinstance(workspace, NoCapabilityWorkspace)
    assert asyncio.run(workspace.list_tools()) == []
