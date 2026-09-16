from fastapi import APIRouter, Depends, Request, Response, status

from ..platform.config import settings
from ..platform.errors import ErrorCode, ForbiddenError, UnauthorizedError
from .application import IssuedSession
from .dependencies import AuthServiceDep, CurrentUser
from .schemas import (
    AccessTokenResponse,
    AuthSessionResponse,
    LoginRequest,
    RegisterRequest,
    UserRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])

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
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
    )
    _set_refresh_cookie(response, issued)
    return _session_response(issued)


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
