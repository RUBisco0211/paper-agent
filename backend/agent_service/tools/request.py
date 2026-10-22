"""Authenticated calls into the business service's narrow internal APIs."""

import httpx

from app.platform.config import settings


class BusinessRequestFailed(Exception):
    """The business service answered with a client-visible error code."""

    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self.code = str(body.get("code") or "internal_error")
        self.message = str(body.get("message") or "")
        super().__init__(f"{self.code}: {self.message}")


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
        if response.is_success:
            return response.json()
        raise BusinessRequestFailed(response.status_code, _body(response))


def _body(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}
