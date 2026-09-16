import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import build_api_router
from .platform.config import settings
from .platform.errors import register_exception_handlers
from .platform.logging import configure_logging
from .platform.request_logging import RequestLoggingMiddleware
from .platform.tasks import AsyncioTaskScheduler

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = AsyncioTaskScheduler()
    scheduler.bind_loop(asyncio.get_running_loop())
    app.state.task_scheduler = scheduler
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
