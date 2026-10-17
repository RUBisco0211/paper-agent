import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Uuid,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from ..platform.errors import (
    ProviderUnavailableError,
    RateLimitedError,
    ValidationError,
)
from .domain import AuthSession, RefreshToken, User, UserCredential


class UserRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSettingsRecord(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)


class AuthSessionRecord(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "auth_sessions"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class RefreshTokenRecord(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "refresh_tokens"

    auth_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("auth_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class AuthRepository:
    """SQLAlchemy persistence for accounts and refresh-token families."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # Users -----------------------------------------------------------------
    def get_user_by_email(self, email: str) -> User | None:
        record = self._session.scalar(
            select(UserRecord).where(UserRecord.email == email),
        )
        return _to_user(record) if record else None

    def get_credential_by_email(self, email: str) -> UserCredential | None:
        record = self._session.scalar(
            select(UserRecord).where(UserRecord.email == email).with_for_update(),
        )
        if record is None:
            return None
        return UserCredential(user=_to_user(record), password_hash=record.password_hash)

    def get_user(self, user_id: UUID) -> User | None:
        record = self._session.get(UserRecord, user_id)
        return _to_user(record) if record else None

    def get_user_for_update(self, user_id: UUID) -> User | None:
        record = self._session.scalar(
            select(UserRecord).where(UserRecord.id == user_id).with_for_update()
        )
        return _to_user(record) if record else None

    def enqueue_verification_email(
        self,
        *,
        recipient: str,
        code: str,
        purpose: str,
        dedupe_key: str,
        expires_at: datetime,
    ) -> None:
        from ..platform.mail import enqueue_email
        from ..platform.mail_templates import verification_email

        subject, html, text_body = verification_email(code, purpose)
        enqueue_email(
            self._session,
            recipient=recipient,
            subject=subject,
            html_body=html,
            text_body=text_body,
            dedupe_key=dedupe_key,
            expires_at=expires_at,
        )

    def enqueue_password_reset_email(self, *, recipient: str, dedupe_key: str) -> None:
        from ..platform.mail import enqueue_email
        from ..platform.mail_templates import password_reset_email

        subject, html, text_body = password_reset_email()
        enqueue_email(
            self._session,
            recipient=recipient,
            subject=subject,
            html_body=html,
            text_body=text_body,
            dedupe_key=dedupe_key,
        )

    def revoke_user_sessions(self, user_id: UUID, *, revoked_at: datetime) -> None:
        self._session.execute(
            update(AuthSessionRecord)
            .where(
                AuthSessionRecord.user_id == user_id,
                AuthSessionRecord.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

    def get_tool_authorizations(self, user_id: UUID) -> dict[str, bool]:
        record = self._session.get(UserSettingsRecord, user_id)
        if record is None:
            return {}
        policies = record.config.get("agent_tools", {}).get("always_allow", {})
        return {
            name: value
            for name, value in policies.items()
            if isinstance(name, str) and isinstance(value, bool)
        }

    def get_timezone(self, user_id: UUID) -> str | None:
        record = self._session.get(UserSettingsRecord, user_id)
        if record is None:
            return None
        timezone = record.config.get("timezone")
        return timezone if isinstance(timezone, str) else None

    def set_timezone(self, user_id: UUID, timezone: str) -> None:
        self._session.execute(
            text(
                "INSERT INTO user_settings (user_id, config) "
                "VALUES (:user_id, jsonb_build_object('version', 1, "
                "'timezone', CAST(:timezone AS text))) "
                "ON CONFLICT (user_id) DO UPDATE SET config = jsonb_set("
                "user_settings.config, '{timezone}', "
                "to_jsonb(CAST(:timezone AS text)), true)"
            ),
            {"user_id": user_id, "timezone": timezone},
        )
        self._session.expire_all()

    def set_tool_authorization(
        self, user_id: UUID, tool_name: str, always_allow: bool
    ) -> None:
        self._session.execute(
            text(
                "INSERT INTO user_settings (user_id, config) "
                "VALUES (:user_id, jsonb_build_object("
                "'version', 1, 'agent_tools', jsonb_build_object("
                "'always_allow', jsonb_build_object("
                "CAST(:tool_name AS text), CAST(:always_allow AS boolean))))) "
                "ON CONFLICT (user_id) DO UPDATE SET config = jsonb_set("
                "user_settings.config, '{agent_tools}', "
                "COALESCE(user_settings.config->'agent_tools', '{}'::jsonb) "
                "|| jsonb_build_object('always_allow', "
                "COALESCE(user_settings.config #> "
                "'{agent_tools,always_allow}', '{}'::jsonb) "
                "|| jsonb_build_object(CAST(:tool_name AS text), "
                "CAST(:always_allow AS boolean))), true)"
            ),
            {
                "user_id": user_id,
                "tool_name": tool_name,
                "always_allow": always_allow,
            },
        )
        self._session.expire_all()

    def add_user(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        email_verified_at: datetime,
    ) -> User:
        record = UserRecord(
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            email_verified_at=email_verified_at,
        )
        self._session.add(record)
        self._session.flush()
        return _to_user(record)

    def update_password_hash(self, user_id: UUID, password_hash: str) -> None:
        record = self._session.get(UserRecord, user_id)
        if record is None:
            return
        record.password_hash = password_hash
        self._session.flush()

    # Sessions --------------------------------------------------------------
    def add_auth_session(self, *, user_id: UUID, expires_at: datetime) -> AuthSession:
        record = AuthSessionRecord(user_id=user_id, expires_at=expires_at)
        self._session.add(record)
        self._session.flush()
        return _to_auth_session(record)

    def get_auth_session(self, auth_session_id: UUID) -> AuthSession | None:
        record = self._session.get(
            AuthSessionRecord, auth_session_id, populate_existing=True
        )
        return _to_auth_session(record) if record else None

    def revoke_auth_session(
        self, auth_session_id: UUID, *, revoked_at: datetime
    ) -> None:
        record = self._session.get(AuthSessionRecord, auth_session_id)
        if record is None or record.revoked_at is not None:
            return
        record.revoked_at = revoked_at
        self._session.flush()

    # Refresh tokens --------------------------------------------------------
    def add_refresh_token(
        self,
        *,
        auth_session_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        record = RefreshTokenRecord(
            auth_session_id=auth_session_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(record)
        self._session.flush()
        return _to_refresh_token(record)

    def get_refresh_token_for_update(self, token_hash: str) -> RefreshToken | None:
        record = self._session.scalar(
            select(RefreshTokenRecord)
            .where(RefreshTokenRecord.token_hash == token_hash)
            .with_for_update(),
        )
        return _to_refresh_token(record) if record else None

    def consume_refresh_token(self, token_id: UUID, *, consumed_at: datetime) -> None:
        record = self._session.get(RefreshTokenRecord, token_id)
        if record is None or record.consumed_at is not None:
            return
        record.consumed_at = consumed_at
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


def _to_user(record: UserRecord) -> User:
    return User(
        id=record.id,
        email=record.email,
        display_name=record.display_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
        email_verified_at=record.email_verified_at,
    )


def _to_auth_session(record: AuthSessionRecord) -> AuthSession:
    return AuthSession(
        id=record.id,
        user_id=record.user_id,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        created_at=record.created_at,
    )


def _to_refresh_token(record: RefreshTokenRecord) -> RefreshToken:
    return RefreshToken(
        id=record.id,
        auth_session_id=record.auth_session_id,
        expires_at=record.expires_at,
        consumed_at=record.consumed_at,
        created_at=record.created_at,
    )


# All keys share one hash tag. This also keeps scripts usable on Redis Cluster.
_ISSUE = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
if tonumber(redis.call('GET', KEYS[2]) or '0') >= 5 then return 0 end
if tonumber(redis.call('GET', KEYS[3]) or '0') >= 20 then return 0 end
local previous = redis.call('GET', KEYS[4])
if previous then redis.call('DEL', previous) end
for i=2,3 do
 local n = redis.call('INCR', KEYS[i])
 if n == 1 then redis.call('EXPIRE', KEYS[i], 3600) end
end
redis.call('SET', KEYS[1], '1', 'EX', ARGV[1])
redis.call('SET', KEYS[4], KEYS[5], 'EX', ARGV[2])
redis.call('HSET', KEYS[5], 'digest', ARGV[3], 'purpose', ARGV[4],
 'payload', ARGV[5], 'attempts', 0, 'active', 0)
redis.call('EXPIRE', KEYS[5], ARGV[2])
return 1
"""
_VERIFY = """
if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end
if redis.call('HGET', KEYS[1], 'active') ~= '1' then return 0 end
if redis.call('HGET', KEYS[1], 'digest') ~= ARGV[1] or
 redis.call('HGET', KEYS[1], 'purpose') ~= ARGV[2] then
 local attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
 if attempts >= tonumber(ARGV[3]) then redis.call('DEL', KEYS[1]) end
 return 0
end
local payload = redis.call('HGET', KEYS[1], 'payload')
redis.call('DEL', KEYS[1])
if cjson.decode(payload)['eligible'] ~= true then return 0 end
redis.call('SET', KEYS[2], payload, 'EX', ARGV[4])
return 1
"""
_CONSUME = """
local payload = redis.call('GET', KEYS[1])
if not payload then return false end
if cjson.decode(payload)['purpose'] ~= ARGV[1] then return false end
redis.call('DEL', KEYS[1])
return payload
"""


class EmailVerificationStore:
    def __init__(
        self,
        redis: Redis,
        *,
        secret: str,
        namespace: str = "auth:{email}",
        ttl: int = 600,
        cooldown: int = 60,
        max_attempts: int = 5,
    ) -> None:
        self.redis = redis
        self.namespace = namespace
        self._secret = secret.encode()
        self.ttl = ttl
        self.cooldown = cooldown
        self.max_attempts = max_attempts

    def _digest(self, value: str) -> str:
        return hmac.new(
            self._secret, ("auth-email:" + value).encode(), hashlib.sha256
        ).hexdigest()

    def _key(self, kind: str, value: str) -> str:
        return f"{self.namespace}:{kind}:{self._digest(value)}"

    def issue(
        self,
        *,
        email: str,
        purpose: str,
        ip: str,
        eligible: bool,
        credential_version: str | None = None,
    ) -> tuple[str, str]:
        challenge_id = secrets.token_urlsafe(32)
        code = f"{secrets.randbelow(1_000_000):06d}"
        payload = json.dumps(
            {
                "email": email,
                "purpose": purpose,
                "eligible": eligible,
                "credential_version": credential_version,
            }
        )
        try:
            issued = self.redis.eval(
                _ISSUE,
                5,
                self._key("cooldown", email),
                self._key("email-limit", email),
                self._key("ip-limit", ip),
                self._key("current", email + ":" + purpose),
                self._key("challenge", challenge_id),
                str(self.cooldown),
                str(self.ttl),
                self._digest(challenge_id + ":" + code),
                purpose,
                payload,
            )
        except RedisError as exc:
            raise ProviderUnavailableError("验证服务暂时不可用，请稍后重试") from exc
        if not issued:
            raise RateLimitedError("发送过于频繁，请稍后重试")
        return challenge_id, code

    def activate(self, challenge_id: str) -> None:
        # A committed outbox row must exist before a real challenge is usable.
        # If either side crashes, the user requests a new code after cooldown.
        try:
            self.redis.eval(
                "if redis.call('EXISTS', KEYS[1]) == 1 then "
                "return redis.call('HSET', KEYS[1], 'active', 1) end return 0",
                1,
                self._key("challenge", challenge_id),
            )
        except RedisError as exc:
            raise ProviderUnavailableError("验证服务暂时不可用，请稍后重试") from exc

    def verify(self, *, challenge_id: str, code: str, purpose: str) -> str:
        token = secrets.token_urlsafe(32)
        try:
            verified = self.redis.eval(
                _VERIFY,
                2,
                self._key("challenge", challenge_id),
                self._key("grant", token),
                self._digest(challenge_id + ":" + code),
                purpose,
                str(self.max_attempts),
                str(self.ttl),
            )
        except RedisError as exc:
            raise ProviderUnavailableError("验证服务暂时不可用，请稍后重试") from exc
        if not verified:
            raise ValidationError("验证码无效或已过期，请重新获取")
        return token

    def consume(self, token: str, *, purpose: str) -> dict:
        try:
            payload = cast(
                str | bytes | None,
                self.redis.eval(_CONSUME, 1, self._key("grant", token), purpose),
            )
        except RedisError as exc:
            raise ProviderUnavailableError("验证服务暂时不可用，请稍后重试") from exc
        if not payload:
            raise ValidationError("验证已失效，请重新获取验证码")
        return json.loads(payload)
