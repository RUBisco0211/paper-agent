from time import perf_counter
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware:
    """Emit one structured completion record for every HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        except Exception as exc:
            logger.error(
                "http.request.failed",
                **self._fields(scope, status_code, started_at),
                error_type=type(exc).__name__,
            )
            raise
        else:
            fields = self._fields(scope, status_code, started_at)
            if status_code >= 500:
                logger.error("http.request.completed", **fields)
            elif status_code >= 400:
                logger.warning("http.request.completed", **fields)
            else:
                logger.info("http.request.completed", **fields)

    @staticmethod
    def _fields(
        scope: Scope,
        status_code: int,
        started_at: float,
    ) -> dict[str, Any]:
        route = scope.get("route")
        route_path = getattr(route, "path", None)
        client = scope.get("client")
        client_ip = client[0] if client else None
        return {
            "method": scope["method"],
            "path": scope["path"],
            "route": route_path,
            "status_code": status_code,
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            "client_ip": client_ip,
        }
