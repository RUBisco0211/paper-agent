"""Account persistence required by the authentication service."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from .domain import AuthSession, RefreshToken, User, UserCredential


class AuthStore(Protocol):
    def get_timezone(self, user_id: UUID) -> str | None: ...

    def set_timezone(self, user_id: UUID, timezone: str) -> None: ...

    def get_notify_email_default(self, user_id: UUID) -> bool: ...

    def set_notify_email_default(self, user_id: UUID, enabled: bool) -> None: ...

    def get_tool_authorizations(self, user_id: UUID) -> dict[str, bool]: ...

    def set_tool_authorization(
        self, user_id: UUID, tool_name: str, always_allow: bool
    ) -> None: ...
    def get_user_by_email(self, email: str) -> User | None: ...

    def get_credential_by_email(self, email: str) -> UserCredential | None: ...

    def get_user(self, user_id: UUID) -> User | None: ...

    def add_user(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        email_verified_at: datetime,
    ) -> User: ...

    def add_auth_session(
        self, *, user_id: UUID, expires_at: datetime
    ) -> AuthSession: ...

    def get_auth_session(self, auth_session_id: UUID) -> AuthSession | None: ...

    def revoke_auth_session(
        self, auth_session_id: UUID, *, revoked_at: datetime
    ) -> None: ...

    def add_refresh_token(
        self, *, auth_session_id: UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken: ...

    def get_refresh_token_for_update(self, token_hash: str) -> RefreshToken | None: ...

    def consume_refresh_token(
        self, token_id: UUID, *, consumed_at: datetime
    ) -> None: ...

    def get_user_for_update(self, user_id: UUID) -> User | None: ...

    def update_password_hash(self, user_id: UUID, password_hash: str) -> None: ...

    def revoke_user_sessions(self, user_id: UUID, *, revoked_at: datetime) -> None: ...

    def enqueue_verification_email(
        self,
        *,
        recipient: str,
        code: str,
        purpose: str,
        dedupe_key: str,
        expires_at: datetime,
    ) -> None: ...

    def enqueue_password_reset_email(
        self, *, recipient: str, dedupe_key: str
    ) -> None: ...

    def rollback(self) -> None: ...

    def commit(self) -> None: ...
