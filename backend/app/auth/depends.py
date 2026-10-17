from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis

from ..platform.config import settings
from ..platform.database import SessionDep
from ..platform.errors import ErrorCode, UnauthorizedError
from ..platform.security import decode_access_token
from .domain import User
from .repo import AuthRepository, EmailVerificationStore
from .service import AuthService

bearer_scheme = HTTPBearer(auto_error=False, description="Access token")


def get_auth_repository(session: SessionDep) -> AuthRepository:
    return AuthRepository(session)


AuthRepositoryDep = Annotated[AuthRepository, Depends(get_auth_repository)]


def get_email_verification_store() -> Iterator[EmailVerificationStore]:
    with Redis.from_url(
        settings.redis_url, socket_connect_timeout=3, socket_timeout=3
    ) as redis:
        yield EmailVerificationStore(
            redis,
            secret=settings.jwt_secret_key,
            ttl=settings.email_verification_ttl_seconds,
            cooldown=settings.email_resend_cooldown_seconds,
            max_attempts=settings.email_verification_max_attempts,
        )


def get_auth_service(
    repository: AuthRepositoryDep,
    verification_store: Annotated[
        EmailVerificationStore, Depends(get_email_verification_store)
    ],
) -> AuthService:
    return AuthService(repository, verification_store=verification_store)


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
