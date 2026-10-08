"""Password hashing and token primitives.

Passwords use Argon2id. Access tokens are short-lived JWTs; refresh tokens are
high-entropy random values that are only stored as a SHA-256 hash.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import settings
from .errors import ErrorCode, UnauthorizedError

_password_hasher = PasswordHasher()

ACCESS_TOKEN_TYPE = "access"
JWT_ISSUER = "paper-agent"
IMPORT_CANDIDATE_TOKEN_TYPE = "import_candidate"


def create_candidate_token(
    *,
    user_id: str,
    session_id: str,
    identifier: str,
    source_id: str | None = None,
    openalex_id: str | None = None,
) -> str:
    candidate_source = source_id or openalex_id
    expires = datetime.now(UTC) + timedelta(minutes=30)
    return jwt.encode(
        {
            "typ": IMPORT_CANDIDATE_TOKEN_TYPE,
            "iss": JWT_ISSUER,
            "uid": user_id,
            "sid": session_id,
            "source_id": candidate_source,
            "identifier": identifier,
            "exp": int(expires.timestamp()),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def read_candidate_token(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=JWT_ISSUER,
        )
        if claims.get("typ") != IMPORT_CANDIDATE_TOKEN_TYPE:
            raise ValueError("wrong token type")
        return claims
    except (jwt.PyJWTError, ValueError) as exc:
        from .errors import ForbiddenError

        raise ForbiddenError("候选文献授权已失效") from exc


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: UUID
    auth_session_id: UUID
    expires_at: datetime


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def create_access_token(
    *,
    user_id: UUID,
    auth_session_id: UUID,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "jti": uuid4().hex,
        "sid": str(auth_session_id),
        "typ": ACCESS_TOKEN_TYPE,
        "iss": JWT_ISSUER,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def decode_access_token(token: str) -> AccessTokenClaims:
    invalid = UnauthorizedError(
        "登录态无效或已过期，请重新登录",
        code=ErrorCode.UNAUTHORIZED,
    )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "sub", "sid", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise invalid from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise invalid
    try:
        return AccessTokenClaims(
            user_id=UUID(payload["sub"]),
            auth_session_id=UUID(payload["sid"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise invalid from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
