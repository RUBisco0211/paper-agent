"""Authenticated calls into the business service's narrow internal APIs."""

import httpx

from app.platform.config import settings


async def business_request(method: str, path: str, **kwargs) -> dict:
    if not settings.agent_internal_key:
        raise RuntimeError("AGENT_INTERNAL_KEY is required for agent tools")
    async with httpx.AsyncClient(
        base_url=settings.business_api_url.rstrip("/"), timeout=20.0
    ) as client:
        response = await client.request(
            method,
            f"{settings.api_prefix}/internal/{path}",
            headers={"X-Agent-Internal-Key": settings.agent_internal_key},
            **kwargs,
        )
        response.raise_for_status()
        return response.json()
