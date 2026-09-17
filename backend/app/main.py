import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import build_api_router
from .platform.config import settings
from .platform.database import SessionLocal
from .platform.errors import register_exception_handlers
from .platform.logging import configure_logging
from .platform.request_logging import RequestLoggingMiddleware
from .platform.storage import get_object_storage
from .platform.tasks import AsyncioTaskScheduler
from .sessions.entries import EntryStore
from .sessions.events import EventBroker
from .sessions.executor import SessionExecutor

configure_logging()
logger = structlog.get_logger(__name__)


def check_embedding_dimensions() -> None:
    """配置的向量维度必须与迁移建的列一致，否则写入会在数据库层失败。"""
    from .platform.database import SessionLocal
    from .retrieval.persistence import chunk_embedding_dimension

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    check_embedding_dimensions()
    scheduler = AsyncioTaskScheduler()
    scheduler.bind_loop(asyncio.get_running_loop())
    broker = EventBroker(buffer_size=settings.session_event_buffer_size)
    executor = SessionExecutor(
        entries=EntryStore(get_object_storage()),
        events=broker,
        session_factory=SessionLocal,
        scheduler=scheduler,
    )
    app.state.task_scheduler = scheduler
    app.state.event_broker = broker
    app.state.session_executor = executor
    try:
        yield
    finally:
        await scheduler.shutdown()


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
