import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import build_api_router
from .platform.config import settings
from .platform.errors import register_exception_handlers
from .platform.logging import configure_logging
from .platform.redis import close_redis
from .platform.request_logging import RequestLoggingMiddleware
from .platform.storage import get_object_storage
from .platform.tasks import ApiTaskScheduler, AsyncioTaskScheduler

configure_logging()
logger = structlog.get_logger(__name__)


def check_embedding_dimensions() -> None:
    """配置的向量维度必须与迁移建的列一致，否则写入会在数据库层失败。"""
    from .platform.database import SessionLocal
    from .retrieval.repo import chunk_embedding_dimension

    try:
        with SessionLocal() as session:
            column_dimension = chunk_embedding_dimension(session)
    except Exception as exc:  # 数据库尚未迁移等情况：启动不因此失败
        logger.warning(
            "configuration.embedding_check_skipped", error=type(exc).__name__
        )
        return

    if (
        column_dimension is not None
        and column_dimension != settings.embedding_dimensions
    ):
        logger.error(
            "configuration.embedding_dimension_mismatch",
            configured=settings.embedding_dimensions,
            column=column_dimension,
            hint="改 EMBEDDING_DIMENSIONS 后需要一次离线迁移（见 backend/README）",
        )


def check_jwt_secret() -> None:
    """弱密钥等于允许伪造登录令牌；生产环境直接拒绝启动。"""
    problem = settings.jwt_secret_problem
    if problem is None:
        return
    logger.error(
        "configuration.weak_jwt_secret",
        problem=problem,
        hint="生成随机密钥：openssl rand -hex 32，只写进 backend/.env",
    )
    if settings.environment != "development":
        raise RuntimeError(
            f"JWT_SECRET_KEY 不可用（{problem}）：部署前请设置随机密钥",
        )


def check_agent_internal_key() -> None:
    if settings.environment != "development" and len(settings.agent_internal_key) < 32:
        raise RuntimeError("AGENT_INTERNAL_KEY 必须配置为至少 32 字符")


def check_credential_master_key() -> None:
    """缺主密钥时每个凭据请求都会 500，所以启动就要拦住。"""
    encoded = settings.credential_master_key.get_secret_value()
    try:
        valid = len(bytes.fromhex(encoded)) == 32
    except ValueError:
        valid = False
    if valid:
        return
    logger.error(
        "configuration.invalid_credential_master_key",
        hint="生成随机密钥：openssl rand -hex 32，只写进 backend/.env",
    )
    raise RuntimeError(
        "CREDENTIAL_MASTER_KEY 必须是 32 字节随机数的十六进制串："
        "请在 backend/.env 设置后重启；已有凭据需沿用原密钥",
    )


def check_storage() -> None:
    """启动时确认对象存储可用（会顺带创建缺失的 bucket）。"""
    backend = settings.storage_backend
    if settings.environment != "development" and backend != "s3":
        raise RuntimeError("生产环境必须配置 S3 兼容对象存储")
    try:
        storage = get_object_storage()
        probe = "system/startup-probe"
        storage.put_bytes(probe, b"ok")
        storage.delete(probe)
    except Exception as exc:
        logger.error(
            "configuration.storage_unavailable",
            backend=backend,
            error=type(exc).__name__,
        )
        raise RuntimeError("对象存储不可用，无法启动业务服务") from exc
    logger.info(
        "configuration.storage_ready",
        backend=backend,
        bucket=settings.s3_bucket if backend == "s3" else str(settings.storage_root),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    check_jwt_secret()
    check_agent_internal_key()
    check_credential_master_key()
    check_embedding_dimensions()
    check_storage()
    scheduler = AsyncioTaskScheduler()
    scheduler.bind_loop(asyncio.get_running_loop())
    app.state.task_scheduler = ApiTaskScheduler(scheduler)
    try:
        yield
    finally:
        await scheduler.shutdown()
        close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Paper Agent 后端 API：个人论文库、项目范围与论文证据问答。",
        lifespan=lifespan,
    )

    # Last added is outermost: CORS wraps correlation IDs, which wrap logging.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CorrelationIdMiddleware,
        header_name="X-Request-ID",
        update_request_header=True,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
            expose_headers=["X-Request-ID"],
        )

    register_exception_handlers(app)
    app.include_router(build_api_router())

    @app.get("/health", tags=["system"], summary="服务健康检查")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "version": settings.app_version}

    @app.get(
        f"{settings.api_prefix}/health",
        tags=["system"],
        summary="服务健康检查",
    )
    def versioned_health_check() -> dict[str, str]:
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
