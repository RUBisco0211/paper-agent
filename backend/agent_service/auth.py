"""Resolve AgentScope ownership from the business service's access token."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.platform.errors import UnauthorizedError
from app.platform.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_agent_service_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> str:
    """Validate the shared JWT without reading the business user database."""
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
    return str(claims.user_id)
