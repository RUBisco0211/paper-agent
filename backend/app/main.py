from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI

from .platform.logging import configure_logging
from .platform.request_logging import RequestLoggingMiddleware

configure_logging()

app = FastAPI(
    title="Paper Agent API",
    version="0.1.0",
    description="Paper Agent 后端 API：个人论文库、项目范围与论文证据问答。",
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware, header_name="X-Request-ID")


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
