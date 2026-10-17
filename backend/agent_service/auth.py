"""Resolve AgentScope ownership from the business service's access token."""

from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.platform.config import settings
from app.platform.errors import UnauthorizedError
from app.platform.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_agent_service_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> str:
    """Validate JWT, then check the live business session without shared DB state."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_access_token",
        )
    try:
        claims = decode_access_token(credentials.credentials)
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_access_token",
        ) from exc
    try:
        async with httpx.AsyncClient(
            base_url=settings.business_api_url.rstrip("/"), timeout=10.0
        ) as client:
            response = await client.get(
                f"{settings.api_prefix}/auth/session-status",
                headers={"Authorization": f"Bearer {credentials.credentials}"},
            )
        if response.status_code in {401, 403}:
            raise HTTPException(status_code=401, detail="invalid_access_token")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("user_id") != str(
            claims.user_id
        ):
            raise HTTPException(status_code=401, detail="invalid_access_token")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="auth_service_unavailable") from exc
    return str(claims.user_id)
