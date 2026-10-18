"""AgentScope HTTP service, kept separate from the business API."""

import os
from pathlib import Path

from agentscope.app import create_app
from agentscope.app.deps import get_current_user_id
from agentscope.app.message_bus import InMemoryMessageBus
from agentscope.app.workspace_manager import IsolationPolicy, LocalWorkspaceManager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import make_url

from app.platform.config import settings

from .auth import get_agent_service_user_id
from .paper_agent import PaperAgent
from .quoted_chat import router as quoted_chat_router
from .schedule_api import router as tool_schedule_router
from .schedule_notifications import ScheduleNotificationStorage
from .session_name import router as session_name_router
from .tools import build_agent_tools
from .tools.request import business_request


def create_agent_service_app(database_url: str, workspace_root: Path) -> FastAPI:
    """Build the single-process AgentScope service with durable SQL storage."""
    if settings.environment != "development" and settings.jwt_secret_problem:
        raise RuntimeError("JWT_SECRET_KEY must be configured for agent_service")
    if settings.environment != "development" and len(settings.agent_internal_key) < 32:
        raise RuntimeError("AGENT_INTERNAL_KEY must be configured for agent_service")
    storage = ScheduleNotificationStorage(
        database_url,
        key_provider=lambda: settings.credential_master_key.get_secret_value(),
        create_tables=False,
        auto_migrate=True,
    )

    async def scoped_paper_tools(user_id: str, agent_id: str, session_id: str):
        policy = await business_request(
            "GET", "tool-authorizations", params={"user_id": user_id}
        )
        return await build_agent_tools(
            user_id, agent_id, session_id, always_allow=policy
        )

    # AgentScope requires a workspace binding. Its local manager still uses an
    # agent-level filesystem path; PaperAgent exposes no filesystem tools, and
    # project artifacts must never use that path as their storage boundary.
    app = create_app(
        storage=storage,
        message_bus=InMemoryMessageBus(),
        workspace_manager=LocalWorkspaceManager(
            str(workspace_root),
            isolation=IsolationPolicy.PER_SESSION,
        ),
        title="Paper Agent AgentScope Service",
        extra_agent_tools=scoped_paper_tools,
        custom_agent_cls=PaperAgent,
    )
    app.dependency_overrides[get_current_user_id] = get_agent_service_user_id
    app.include_router(tool_schedule_router)
    app.include_router(quoted_chat_router)
    app.include_router(session_name_router)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
    return app


database_url = os.environ.get("AGENT_SERVICE_DATABASE_URL") or make_url(
    settings.database_url,
).set(database="paper_agent_as").render_as_string(hide_password=False)
app = create_agent_service_app(
    database_url,
    Path(os.environ.get("AGENT_SERVICE_WORKSPACE_ROOT", ".var/agent-workspaces")),
)
