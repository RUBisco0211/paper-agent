from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Uuid,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from .domain import AuthSession, RefreshToken, User, UserCredential


class UserRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)


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
            select(UserRecord).where(UserRecord.email == email),
        )
        if record is None:
            return None
        return UserCredential(user=_to_user(record), password_hash=record.password_hash)

    def get_user(self, user_id: UUID) -> User | None:
        record = self._session.get(UserRecord, user_id)
        return _to_user(record) if record else None

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

    def add_user(self, *, email: str, password_hash: str, display_name: str) -> User:
        record = UserRecord(
            email=email,
            password_hash=password_hash,
            display_name=display_name,
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
        record = self._session.get(AuthSessionRecord, auth_session_id)
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
