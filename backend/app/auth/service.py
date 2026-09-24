from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from ..platform.config import settings
from ..platform.errors import ConflictError, ErrorCode, UnauthorizedError
from ..platform.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from .domain import User, normalize_email, validate_password
from .ports import AuthStore

logger = structlog.get_logger(__name__)

# A real Argon2 hash of a placeholder value. Verifying against it for unknown
# accounts keeps login timing independent of whether the email exists.
_PLACEHOLDER_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$3mdwN6iNsN23hwtonYKp4Q"
    "$gGoXovTrYDfWynS/m5Tp//bQAH7gz5LqJOk+fPkq8/0"
)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    user: User
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    auth_session_id: UUID


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuthService:
    """Account lifecycle: register, login, rotate and revoke."""

    def __init__(
        self,
        repository: AuthStore,
        *,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._repository = repository
        self._now = now

    # Use cases -------------------------------------------------------------
    def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str = "",
    ) -> IssuedSession:
        normalized_email = normalize_email(email)
        validate_password(password)

        if self._repository.get_user_by_email(normalized_email) is not None:
            raise ConflictError(
                "该邮箱已注册",
                code=ErrorCode.EMAIL_ALREADY_REGISTERED,
            )

        user = self._repository.add_user(
            email=normalized_email,
            password_hash=hash_password(password),
            display_name=display_name.strip() or normalized_email.split("@")[0],
        )
        issued = self._issue_session(user)
        self._repository.commit()
        logger.info("service.auth.registered", user_id=str(user.id))
        return issued

    def login(self, *, email: str, password: str) -> IssuedSession:
        normalized_email = normalize_email(email)
        credential = self._repository.get_credential_by_email(normalized_email)
        if credential is None:
            verify_password(password, _PLACEHOLDER_HASH)
            raise _invalid_credentials()

        if not verify_password(password, credential.password_hash):
            logger.info(
                "service.auth.login_rejected",
                user_id=str(credential.user.id),
            )
            raise _invalid_credentials()

        user = credential.user
        issued = self._issue_session(user)
        self._repository.commit()
        logger.info("service.auth.logged_in", user_id=str(user.id))
        return issued

    def refresh(self, refresh_token: str) -> IssuedSession:
        now = self._now()
        stored = self._repository.get_refresh_token_for_update(
            hash_refresh_token(refresh_token),
        )
        if stored is None:
            raise _invalid_refresh_token()

        auth_session = self._repository.get_auth_session(stored.auth_session_id)
        if auth_session is None or not auth_session.is_active:
            raise UnauthorizedError(
                "登录态已失效，请重新登录",
                code=ErrorCode.UNAUTHORIZED,
            )
        if auth_session.expires_at <= now or stored.expires_at <= now:
            raise _invalid_refresh_token()

        if stored.consumed_at is not None:
            # A rotated token is being replayed: assume theft and kill the
            # whole family so the attacker and the victim both have to log in.
            self._repository.revoke_auth_session(auth_session.id, revoked_at=now)
            self._repository.commit()
            logger.warning(
                "service.auth.refresh_reuse_detected",
                auth_session_id=str(auth_session.id),
                user_id=str(auth_session.user_id),
            )
            raise UnauthorizedError(
                "检测到刷新令牌重复使用，已终止该登录会话",
                code=ErrorCode.REFRESH_TOKEN_REUSED,
            )

        user = self._repository.get_user(auth_session.user_id)
        if user is None:
            raise UnauthorizedError("登录态已失效，请重新登录")

        self._repository.consume_refresh_token(stored.id, consumed_at=now)
        issued = self._issue_session(
            user,
            auth_session_id=auth_session.id,
            session_expires_at=auth_session.expires_at,
        )
        self._repository.commit()
        logger.info("service.auth.refreshed", user_id=str(user.id))
        return issued

    def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        stored = self._repository.get_refresh_token_for_update(
            hash_refresh_token(refresh_token),
        )
        if stored is None:
            return
        self._repository.revoke_auth_session(
            stored.auth_session_id,
            revoked_at=self._now(),
        )
        self._repository.commit()
        logger.info(
            "service.auth.logged_out",
            auth_session_id=str(stored.auth_session_id),
        )

    # Internals -------------------------------------------------------------
    def _issue_session(
        self,
        user: User,
        *,
        auth_session_id: UUID | None = None,
        session_expires_at: datetime | None = None,
    ) -> IssuedSession:
        now = self._now()
        if session_expires_at is None:
            session_expires_at = now + timedelta(
                days=settings.refresh_token_ttl_days,
            )
        if auth_session_id is None:
            auth_session = self._repository.add_auth_session(
                user_id=user.id,
                expires_at=session_expires_at,
            )
            auth_session_id = auth_session.id

        refresh_token = generate_refresh_token()
        self._repository.add_refresh_token(
            auth_session_id=auth_session_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=session_expires_at,
        )
        access_token, access_expires_at = create_access_token(
            user_id=user.id,
            auth_session_id=auth_session_id,
            now=now,
        )
        return IssuedSession(
            user=user,
            access_token=access_token,
            access_expires_at=access_expires_at,
            refresh_token=refresh_token,
            refresh_expires_at=session_expires_at,
            auth_session_id=auth_session_id,
        )


def _invalid_credentials() -> UnauthorizedError:
    return UnauthorizedError(
        "邮箱或密码不正确",
        code=ErrorCode.INVALID_CREDENTIALS,
    )


def _invalid_refresh_token() -> UnauthorizedError:
    return UnauthorizedError(
        "刷新令牌无效或已过期，请重新登录",
        code=ErrorCode.REFRESH_TOKEN_INVALID,
    )
