from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .domain import User


class EmailCodeRequest(BaseModel):
    email: EmailStr
    purpose: Literal["register", "password_reset"]


class EmailCodeResponse(BaseModel):
    challenge_id: str
    retry_after: int
    expires_in: int


class EmailCodeVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    purpose: Literal["register", "password_reset"]


class EmailCodeVerifyResponse(BaseModel):
    verification_token: str
    expires_in: int


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)


class RegisterRequest(PasswordResetRequest):
    display_name: str = Field(default="", max_length=120)


class SessionStatusResponse(BaseModel):
    user_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ToolAuthorizationUpdate(BaseModel):
    always_allow: bool


class ToolAuthorizationRead(BaseModel):
    tool_name: str
    always_allow: bool


class TimezoneUpdate(BaseModel):
    timezone: str = Field(min_length=1, max_length=64)


class TimezoneRead(BaseModel):
    timezone: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    created_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> "UserRead":
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            created_at=user.created_at,
        )


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: datetime


class AuthSessionResponse(AccessTokenResponse):
    user: UserRead
