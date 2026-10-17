"""Valid, nonproduction master key for AgentScope integration tests."""

import httpx
import pytest
from pydantic import SecretStr

from app.platform.config import settings


@pytest.fixture(autouse=True)
def credential_master_key_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))


@pytest.fixture
def agent_business_http(client, monkeypatch):
    """Use the real business HTTP app and PostgreSQL for session-status checks."""
    original = httpx.AsyncClient

    def business_client(**kwargs):
        kwargs.setdefault("transport", httpx.ASGITransport(app=client.app))
        return original(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", business_client)


@pytest.fixture
def agent_access_token(register_user, agent_business_http):
    return register_user()["access_token"]
