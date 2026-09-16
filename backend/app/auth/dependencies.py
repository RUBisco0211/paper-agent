from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..platform.database import SessionDep
from ..platform.errors import ErrorCode, UnauthorizedError
from ..platform.security import decode_access_token
from .application import AuthService
from .domain import User
from .persistence import AuthRepository

bearer_scheme = HTTPBearer(auto_error=False, description="Access token")


def get_auth_repository(session: SessionDep) -> AuthRepository:
    return AuthRepository(session)


AuthRepositoryDep = Annotated[AuthRepository, Depends(get_auth_repository)]


def get_auth_service(repository: AuthRepositoryDep) -> AuthService:
    return AuthService(repository)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_current_user(
    session: SessionDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> User:
    """Resolve the authenticated user from the Bearer access token."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("缺少访问令牌", code=ErrorCode.UNAUTHORIZED)

    claims = decode_access_token(credentials.credentials)
    repository = AuthRepository(session)
    auth_session = repository.get_auth_session(claims.auth_session_id)
    if (
        auth_session is None
        or auth_session.user_id != claims.user_id
        or not auth_session.is_active
        or auth_session.expires_at <= datetime.now(UTC)
    ):
        raise UnauthorizedError(
            "登录态已失效，请重新登录",
            code=ErrorCode.UNAUTHORIZED,
        )

    user = repository.get_user(claims.user_id)
    if user is None:
        raise UnauthorizedError("账号不存在", code=ErrorCode.UNAUTHORIZED)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
