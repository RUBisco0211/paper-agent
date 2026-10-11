"""Authenticate narrowly scoped requests from the AgentScope service."""

import secrets
from typing import Annotated

from fastapi import Depends, Header

from .config import settings
from .errors import ErrorCode, UnauthorizedError


def require_agent_internal_key(
    x_agent_internal_key: Annotated[str | None, Header()] = None,
) -> None:
    configured = settings.agent_internal_key
    if (
        not configured
        or not x_agent_internal_key
        or not secrets.compare_digest(configured, x_agent_internal_key)
    ):
        raise UnauthorizedError("内部服务认证失败", code=ErrorCode.UNAUTHORIZED)


AgentInternalAuth = Annotated[None, Depends(require_agent_internal_key)]
