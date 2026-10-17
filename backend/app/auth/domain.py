from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..platform.errors import DomainValidationError

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
REVIEWABLE_AGENT_TOOLS = frozenset({"import_selected_papers", "create_scheduled_task"})


class InvalidEmail(DomainValidationError):
    """Raised when an email address cannot be normalized."""


class InvalidPassword(DomainValidationError):
    """Raised when a password violates the policy."""


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise InvalidEmail("邮箱格式不正确")
    local, _, domain = normalized.partition("@")
    if not local or "." not in domain:
        raise InvalidEmail("邮箱格式不正确")
    if len(normalized) > 320:
        raise InvalidEmail("邮箱过长")
    return normalized


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidPassword(f"密码至少需要 {MIN_PASSWORD_LENGTH} 位")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise InvalidPassword(f"密码不能超过 {MAX_PASSWORD_LENGTH} 位")
    return password


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: str
    display_name: str
    created_at: datetime
    updated_at: datetime
    email_verified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class UserCredential:
    """A user together with the stored password hash, for login only."""

    user: User
    password_hash: str


@dataclass(frozen=True, slots=True)
class AuthSession:
    """One logged-in device; the unit that is revoked on logout."""

    id: UUID
    user_id: UUID
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True, slots=True)
class RefreshToken:
    id: UUID
    auth_session_id: UUID
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime
