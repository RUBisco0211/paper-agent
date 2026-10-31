import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy.exc import IntegrityError

from ..platform.config import settings
from ..platform.errors import (
    ConflictError,
    ErrorCode,
    UnauthorizedError,
    ValidationError,
)
from ..platform.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from .domain import REVIEWABLE_AGENT_TOOLS, User, normalize_email, validate_password
from .ports import AuthStore
from .repo import EmailVerificationStore

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
        verification_store: EmailVerificationStore | None = None,
    ) -> None:
        self._repository = repository
        self._now = now
        self._verification_store = verification_store

    # Use cases -------------------------------------------------------------
    def set_timezone(self, *, user_id: UUID, timezone: str) -> str:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValidationError("时区无效") from exc
        self._repository.set_timezone(user_id, timezone)
        self._repository.commit()
        return timezone

    def preferences(self, user_id: UUID) -> dict:
        return {
            "timezone": self._repository.get_timezone(user_id),
            "notify_email_default": self._repository.get_notify_email_default(user_id),
        }

    def set_notify_email_default(self, *, user_id: UUID, enabled: bool) -> bool:
        self._repository.set_notify_email_default(user_id, enabled)
        self._repository.commit()
        return enabled

    def tool_authorizations(self, user_id: UUID) -> dict[str, bool]:
        stored = self._repository.get_tool_authorizations(user_id)
        return {
            name: stored.get(name, False) for name in sorted(REVIEWABLE_AGENT_TOOLS)
        }

    def set_tool_authorization(
        self, *, user_id: UUID, tool_name: str, always_allow: bool
    ) -> bool:
        if tool_name not in REVIEWABLE_AGENT_TOOLS:
            raise ValidationError("不能配置此工具")
        self._repository.set_tool_authorization(user_id, tool_name, always_allow)
        self._repository.commit()
        return always_allow

    def _verification(self) -> EmailVerificationStore:
        if self._verification_store is None:
            raise RuntimeError("Email verification store is not configured")
        return self._verification_store

    def request_email_code(self, *, email: str, purpose: str, ip: str) -> str:
        email = normalize_email(email)
        credential = self._repository.get_credential_by_email(email)
        if purpose == "register" and credential is not None:
            raise ConflictError(
                "该邮箱已注册",
                code=ErrorCode.EMAIL_ALREADY_REGISTERED,
            )
        eligible = purpose == "register" or credential is not None
        version = (
            hashlib.sha256(credential.password_hash.encode()).hexdigest()
            if credential is not None and purpose == "password_reset"
            else None
        )
        challenge_id, code = self._verification().issue(
            email=email,
            purpose=purpose,
            ip=ip,
            eligible=eligible,
            credential_version=version,
        )
        if eligible:
            self._repository.enqueue_verification_email(
                recipient=email,
                code=code,
                purpose=purpose,
                dedupe_key="auth-code:" + challenge_id,
                expires_at=self._now() + timedelta(seconds=self._verification().ttl),
            )
            self._repository.commit()
        self._verification().activate(challenge_id)
        return challenge_id

    def verify_email_code(self, *, challenge_id: str, code: str, purpose: str) -> str:
        return self._verification().verify(
            challenge_id=challenge_id, code=code, purpose=purpose
        )

    def reset_password(
        self, *, verification_token: str, password: str, password_confirmation: str
    ) -> None:
        self._validate_password_confirmation(password, password_confirmation)
        # Redis is deliberately consumed before the database transaction: a crash
        # may require re-verification, but can never resurrect a reset grant.
        grant = self._verification().consume(
            verification_token, purpose="password_reset"
        )
        credential = self._repository.get_credential_by_email(grant["email"])
        if (
            credential is None
            or hashlib.sha256(credential.password_hash.encode()).hexdigest()
            != grant["credential_version"]
        ):
            raise ValidationError("验证已失效，请重新获取验证码")
        self._repository.update_password_hash(
            credential.user.id, hash_password(password)
        )
        self._repository.revoke_user_sessions(
            credential.user.id, revoked_at=self._now()
        )
        self._repository.enqueue_password_reset_email(
            recipient=credential.user.email,
            dedupe_key="auth-reset:"
            + hashlib.sha256(verification_token.encode()).hexdigest(),
        )
        self._repository.commit()

    @staticmethod
    def _validate_password_confirmation(password: str, confirmation: str) -> None:
        validate_password(password)
        if password != confirmation:
            raise ValidationError("两次输入的密码不一致")

    def register(
        self,
        *,
        verification_token: str,
        password: str,
        password_confirmation: str,
        display_name: str = "",
    ) -> IssuedSession:
        self._validate_password_confirmation(password, password_confirmation)
        grant = self._verification().consume(verification_token, purpose="register")
        normalized_email = grant["email"]

        if self._repository.get_user_by_email(normalized_email) is not None:
            raise ConflictError(
                "该邮箱已注册",
                code=ErrorCode.EMAIL_ALREADY_REGISTERED,
            )

        try:
            user = self._repository.add_user(
                email=normalized_email,
                password_hash=hash_password(password),
                display_name=display_name.strip() or normalized_email.split("@")[0],
                email_verified_at=self._now(),
            )
            issued = self._issue_session(user)
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            if self._repository.get_user_by_email(normalized_email) is None:
                raise
            raise ConflictError(
                "该邮箱已注册", code=ErrorCode.EMAIL_ALREADY_REGISTERED
            ) from exc
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

        user = self._repository.get_user_for_update(auth_session.user_id)
        auth_session = self._repository.get_auth_session(stored.auth_session_id)
        if user is None or auth_session is None or not auth_session.is_active:
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
