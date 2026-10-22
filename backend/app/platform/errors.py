"""Stable error contract shared by every endpoint.

HTTP status codes express the error class; the JSON body always carries a
stable snake_case ``code``, a human readable ``message`` and the ``request_id``
of the request so a client can correlate it with server logs.
"""

from enum import StrEnum
from typing import Any

from asgi_correlation_id import correlation_id
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(StrEnum):
    # Generic
    VALIDATION_ERROR = "validation_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"
    NOT_IMPLEMENTED = "not_implemented"

    # Authentication
    EMAIL_ALREADY_REGISTERED = "email_already_registered"
    INVALID_CREDENTIALS = "invalid_credentials"
    REFRESH_TOKEN_MISSING = "refresh_token_missing"
    REFRESH_TOKEN_INVALID = "refresh_token_invalid"
    REFRESH_TOKEN_REUSED = "refresh_token_reused"
    ORIGIN_NOT_ALLOWED = "origin_not_allowed"

    # Library
    PAPER_NOT_FOUND = "paper_not_found"
    PAPER_PDF_NOT_AVAILABLE = "paper_pdf_not_available"
    PDF_INVALID = "pdf_invalid"
    PDF_ENCRYPTED = "pdf_encrypted"
    PDF_UNREADABLE = "pdf_unreadable"
    PDF_TOO_LARGE = "pdf_too_large"
    PDF_TOO_MANY_PAGES = "pdf_too_many_pages"
    METADATA_NOT_FOUND = "metadata_not_found"
    METADATA_PROVIDER_FAILED = "metadata_provider_failed"
    METADATA_CONFLICT = "metadata_conflict"
    DUPLICATE_IDENTIFIER = "duplicate_identifier"

    # Ingestion
    INGESTION_JOB_NOT_FOUND = "ingestion_job_not_found"
    INGESTION_ALREADY_RUNNING = "ingestion_already_running"
    INGESTION_STAGE_FAILED = "ingestion_stage_failed"
    INGESTION_NOTHING_TO_RETRY = "ingestion_nothing_to_retry"
    INGESTION_ARTIFACT_INVALID = "ingestion_artifact_invalid"

    # Projects
    PROJECT_NOT_FOUND = "project_not_found"
    PROJECT_PAPER_ALREADY_ADDED = "project_paper_already_added"

    # Sessions
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_BUSY = "session_busy"
    SESSION_NOT_GENERATING = "session_not_generating"
    ENTRY_NOT_FOUND = "entry_not_found"
    CITATION_NOT_FOUND = "citation_not_found"
    PENDING_MESSAGE_NOT_FOUND = "pending_message_not_found"
    AGENT_UNAVAILABLE = "agent_unavailable"
    AGENT_TIMEOUT = "agent_timeout"
    AGENT_MAX_ITERS = "agent_max_iters"
    LLM_NOT_CONFIGURED = "llm_not_configured"

    # Retrieval
    RETRIEVAL_UNAVAILABLE = "retrieval_unavailable"
    EVIDENCE_NOT_AVAILABLE = "evidence_not_available"

    # Imports
    IMPORT_NOT_FOUND = "import_not_found"
    IDENTIFIER_INVALID = "identifier_invalid"
    IDENTIFIER_NOT_RESOLVED = "identifier_not_resolved"

    # Providers
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_QUOTA_EXHAUSTED = "provider_quota_exhausted"


class DomainValidationError(ValueError):
    """Base class for domain invariants that map to a 422 response.

    Domains raise these without importing HTTP details; the handler below turns
    them into the shared error contract.
    """


class AppError(Exception):
    """Base class for every expected, client-visible failure."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    message: str = "服务内部错误"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: ErrorCode | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    code = ErrorCode.NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND
    message = "资源不存在"


class ConflictError(AppError):
    code = ErrorCode.CONFLICT
    status_code = status.HTTP_409_CONFLICT
    message = "资源冲突"


class UnauthorizedError(AppError):
    code = ErrorCode.UNAUTHORIZED
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "未认证或登录态已失效"


class ForbiddenError(AppError):
    code = ErrorCode.FORBIDDEN
    status_code = status.HTTP_403_FORBIDDEN
    message = "没有访问该资源的权限"


class ValidationError(AppError):
    code = ErrorCode.VALIDATION_ERROR
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "请求参数不合法"


class RateLimitedError(AppError):
    code = ErrorCode.RATE_LIMITED
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    message = "请求过于频繁，请稍后重试"


class ProviderUnavailableError(AppError):
    code = ErrorCode.PROVIDER_UNAVAILABLE
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "上游服务暂时不可用"


class NotImplementedAppError(AppError):
    code = ErrorCode.NOT_IMPLEMENTED
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    message = "该能力尚未实现"


class ProviderNotConfiguredError(AppError):
    code = ErrorCode.PROVIDER_NOT_CONFIGURED
    status_code = status.HTTP_409_CONFLICT
    message = "api key unavailable"


def error_body(error: AppError) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": str(error.code),
        "message": error.message,
        "request_id": correlation_id.get(),
    }
    if error.details is not None:
        body["details"] = error.details
    return body


def _json_error(
    error: AppError, *, ensure_request_id_header: bool = False
) -> JSONResponse:
    """Render an error body.

    ``X-Request-ID`` is normally appended by ``CorrelationIdMiddleware``. Only
    the handler for unhandled exceptions has to add it explicitly, because that
    response is produced outside the middleware stack.
    """
    headers: dict[str, str] = {}
    if ensure_request_id_header and (request_id := correlation_id.get()):
        headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=error.status_code,
        content=error_body(error),
        headers=headers or None,
    )


_STATUS_TO_CODE = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.VALIDATION_ERROR,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.VALIDATION_ERROR,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_413_CONTENT_TOO_LARGE: ErrorCode.PAYLOAD_TOO_LARGE,
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: ErrorCode.VALIDATION_ERROR,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return _json_error(exc)

    @app.exception_handler(DomainValidationError)
    async def handle_domain_validation_error(
        _request: Request,
        exc: DomainValidationError,
    ) -> JSONResponse:
        return _json_error(ValidationError(str(exc)))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        error = ValidationError(details=exc.errors())
        return _json_error(error)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return _json_error(
            AppError(message, code=code, status_code=exc.status_code),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        # The stack trace is logged where it happens; the client only gets a
        # stable code so internal details never leak.
        error = AppError(
            "服务内部错误",
            code=ErrorCode.INTERNAL_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return _json_error(error, ensure_request_id_header=True)
