"""Authenticated HTTP adapter for AgentScope's internal schedule operations."""

import httpx

from .config import settings
from .errors import (
    AppError,
    ConflictError,
    ErrorCode,
    NotFoundError,
    ProviderUnavailableError,
)


class HttpAgentScheduleGateway:
    def _request(self, method: str, path: str, **kwargs) -> dict:
        if not settings.agent_internal_key:
            raise ProviderUnavailableError("内部任务服务未配置")
        try:
            with httpx.Client(
                base_url=settings.agent_service_url.rstrip("/"), timeout=20.0
            ) as client:
                response = client.request(
                    method,
                    path,
                    headers={"X-Agent-Internal-Key": settings.agent_internal_key},
                    **kwargs,
                )
                if response.status_code == 409:
                    try:
                        detail = response.json().get("detail")
                    except ValueError:
                        detail = None
                    if detail == "llm_not_configured":
                        raise AppError(
                            "当前会话尚未配置模型",
                            code=ErrorCode.LLM_NOT_CONFIGURED,
                            status_code=409,
                        )
                    if detail == "unattended_run":
                        raise ConflictError("不能在定时任务运行中创建新任务")
                if response.status_code == 404:
                    try:
                        detail = response.json().get("detail")
                    except ValueError:
                        detail = None
                    if detail == "session_not_found":
                        raise NotFoundError(
                            "会话不存在", code=ErrorCode.SESSION_NOT_FOUND
                        )
                    raise NotFoundError("定时任务不存在")
                response.raise_for_status()
                return response.json() if response.content else {}
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("定时任务服务暂时不可用") from exc

    def create_disabled(self, **kwargs) -> str:
        result = self._request("POST", "/internal/tool-schedules", json=kwargs)
        return str(result["schedule_id"])

    def enable(self, *, user_id: str, schedule_id: str) -> None:
        self._request(
            "POST",
            f"/internal/tool-schedules/{schedule_id}/enable",
            json={"user_id": user_id},
        )

    def delete(self, *, user_id: str, schedule_id: str) -> None:
        self._request(
            "DELETE",
            f"/internal/tool-schedules/{schedule_id}",
            json={"user_id": user_id},
        )
