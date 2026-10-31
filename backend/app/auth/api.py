from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from ..platform.config import settings
from ..platform.errors import ErrorCode, ForbiddenError, UnauthorizedError
from ..platform.internal_auth import AgentInternalAuth
from .depends import AuthServiceDep, CurrentUser
from .schemas import (
    AccessTokenResponse,
    AuthSessionResponse,
    EmailCodeRequest,
    EmailCodeResponse,
    EmailCodeVerifyRequest,
    EmailCodeVerifyResponse,
    LoginRequest,
    PasswordResetRequest,
    RegisterRequest,
    SessionStatusResponse,
    PreferencesRead,
    PreferencesUpdate,
    TimezoneRead,
    TimezoneUpdate,
    ToolAuthorizationRead,
    ToolAuthorizationUpdate,
    UserRead,
)
from .service import IssuedSession

router = APIRouter(prefix="/auth", tags=["auth"])
internal_router = APIRouter(tags=["auth"])

REFRESH_COOKIE_PATH = f"{settings.api_prefix}/auth"


def verify_request_origin(request: Request) -> None:
    """Reject cookie-authenticated writes coming from another site."""
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_origins:
        raise ForbiddenError(
            "请求来源不被允许",
            code=ErrorCode.ORIGIN_NOT_ALLOWED,
        )


def _set_refresh_cookie(response: Response, issued: IssuedSession) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=issued.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        domain=settings.refresh_cookie_domain,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        domain=settings.refresh_cookie_domain,
    )


def _session_response(issued: IssuedSession) -> AuthSessionResponse:
    return AuthSessionResponse(
        access_token=issued.access_token,
        expires_in=settings.access_token_ttl_minutes * 60,
        expires_at=issued.access_expires_at,
        user=UserRead.from_domain(issued.user),
    )


@router.post(
    "/register",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册并建立登录态",
)
def register(
    payload: RegisterRequest,
    response: Response,
    service: AuthServiceDep,
) -> AuthSessionResponse:
    issued = service.register(
        verification_token=payload.verification_token,
        password=payload.password,
        password_confirmation=payload.password_confirmation,
        display_name=payload.display_name,
    )
    _set_refresh_cookie(response, issued)
    return _session_response(issued)


@router.post("/email-codes", response_model=EmailCodeResponse)
def request_email_code(
    payload: EmailCodeRequest, request: Request, service: AuthServiceDep
) -> EmailCodeResponse:
    challenge_id = service.request_email_code(
        email=payload.email,
        purpose=payload.purpose,
        ip=request.client.host if request.client else "unknown",
    )
    return EmailCodeResponse(
        challenge_id=challenge_id,
        retry_after=settings.email_resend_cooldown_seconds,
        expires_in=settings.email_verification_ttl_seconds,
    )


@router.post("/email-codes/verify", response_model=EmailCodeVerifyResponse)
def verify_email_code(
    payload: EmailCodeVerifyRequest, service: AuthServiceDep
) -> EmailCodeVerifyResponse:
    token = service.verify_email_code(
        challenge_id=payload.challenge_id, code=payload.code, purpose=payload.purpose
    )
    return EmailCodeVerifyResponse(
        verification_token=token, expires_in=settings.email_verification_ttl_seconds
    )


@router.post("/password-reset", status_code=204)
def reset_password(
    payload: PasswordResetRequest, response: Response, service: AuthServiceDep
) -> Response:
    service.reset_password(
        verification_token=payload.verification_token,
        password=payload.password,
        password_confirmation=payload.password_confirmation,
    )
    _clear_refresh_cookie(response)
    response.status_code = 204
    return response


@router.get("/session-status", response_model=SessionStatusResponse)
def session_status(user: CurrentUser) -> SessionStatusResponse:
    return SessionStatusResponse(user_id=str(user.id))


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    summary="登录",
)
def login(
    payload: LoginRequest,
    response: Response,
    service: AuthServiceDep,
) -> AuthSessionResponse:
    issued = service.login(email=payload.email, password=payload.password)
    _set_refresh_cookie(response, issued)
    return _session_response(issued)


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="轮换刷新令牌并获取新的访问令牌",
    dependencies=[Depends(verify_request_origin)],
)
def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> AccessTokenResponse:
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        raise UnauthorizedError(
            "缺少刷新令牌",
            code=ErrorCode.REFRESH_TOKEN_MISSING,
        )
    issued = service.refresh(refresh_token)
    _set_refresh_cookie(response, issued)
    payload = _session_response(issued)
    return AccessTokenResponse(
        access_token=payload.access_token,
        expires_in=payload.expires_in,
        expires_at=payload.expires_at,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="退出当前登录设备",
    dependencies=[Depends(verify_request_origin)],
)
def logout(
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> Response:
    service.logout(request.cookies.get(settings.refresh_cookie_name))
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get(
    "/me",
    response_model=UserRead,
    summary="读取当前账号",
)
def read_current_user(user: CurrentUser) -> UserRead:
    return UserRead.from_domain(user)


@router.get("/tool-authorizations", response_model=dict[str, bool])
def read_tool_authorizations(
    user: CurrentUser, service: AuthServiceDep
) -> dict[str, bool]:
    return service.tool_authorizations(user.id)


@router.get("/preferences", response_model=PreferencesRead)
def read_preferences(user: CurrentUser, service: AuthServiceDep) -> PreferencesRead:
    return PreferencesRead(**service.preferences(user.id))


@router.patch("/preferences", response_model=PreferencesRead)
def update_preferences(
    payload: PreferencesUpdate, user: CurrentUser, service: AuthServiceDep
) -> PreferencesRead:
    service.set_notify_email_default(
        user_id=user.id, enabled=payload.notify_email_default
    )
    return PreferencesRead(**service.preferences(user.id))


@router.patch("/timezone", response_model=TimezoneRead)
def update_timezone(
    payload: TimezoneUpdate, user: CurrentUser, service: AuthServiceDep
) -> TimezoneRead:
    return TimezoneRead(
        timezone=service.set_timezone(user_id=user.id, timezone=payload.timezone)
    )


@router.patch("/tool-authorizations/{tool_name}", response_model=ToolAuthorizationRead)
def update_tool_authorization(
    tool_name: str,
    payload: ToolAuthorizationUpdate,
    user: CurrentUser,
    service: AuthServiceDep,
) -> ToolAuthorizationRead:
    allowed = service.set_tool_authorization(
        user_id=user.id, tool_name=tool_name, always_allow=payload.always_allow
    )
    return ToolAuthorizationRead(tool_name=tool_name, always_allow=allowed)


@internal_router.get("/internal/tool-authorizations", response_model=dict[str, bool])
def read_internal_tool_authorizations(
    user_id: UUID, _auth: AgentInternalAuth, service: AuthServiceDep
) -> dict[str, bool]:
    return service.tool_authorizations(user_id)
