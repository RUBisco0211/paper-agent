"""Scheduled-run scope binding before agent assembly."""

import httpx
from agentscope.app.storage import SessionSource, StorageBase

from app.platform.config import settings


async def prepare_schedule_scope(
    storage: StorageBase,
    user_id: str,
    agent_id: str,
    session_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    session = await storage.get_session(user_id, agent_id, session_id)
    if session is None:
        raise RuntimeError("Scheduled session is unavailable")
    if session.source != SessionSource.SCHEDULE:
        return
    if not session.source_schedule_id or not settings.agent_internal_key:
        raise RuntimeError("Scheduled session scope is unavailable")

    async def bind(http: httpx.AsyncClient) -> None:
        response = await http.post(
            f"{settings.api_prefix}/internal/schedule-sessions",
            headers={"X-Agent-Internal-Key": settings.agent_internal_key},
            json={
                "user_id": user_id,
                "session_id": session_id,
                "schedule_id": session.source_schedule_id,
            },
        )
        response.raise_for_status()

    if client is not None:
        await bind(client)
    else:
        async with httpx.AsyncClient(
            base_url=settings.business_api_url.rstrip("/"), timeout=20.0
        ) as http:
            await bind(http)
