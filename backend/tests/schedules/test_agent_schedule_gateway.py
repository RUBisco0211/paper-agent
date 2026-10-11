"""The schedule gateway preserves useful AgentScope errors without leaking bodies."""

import httpx
import pytest

from app.platform.agent_schedules import HttpAgentScheduleGateway
from app.platform.config import settings
from app.platform.errors import AppError, ErrorCode


def test_schedule_gateway_reports_missing_session_model_as_a_model_error(monkeypatch):
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    original_client = httpx.Client
    transport = httpx.MockTransport(
        lambda request: httpx.Response(409, json={"detail": "llm_not_configured"})
    )
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs)
    )
    with pytest.raises(AppError) as error:
        HttpAgentScheduleGateway().create_disabled(
            user_id="user",
            agent_id="agent",
            session_id="session",
            name="Review",
            prompt="Read",
            cron_expression="0 9 * * MON",
            timezone="Asia/Shanghai",
        )
    assert error.value.code == ErrorCode.LLM_NOT_CONFIGURED
