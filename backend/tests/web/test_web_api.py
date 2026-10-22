"""The internal web endpoints answer the agent service and enforce its key."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.platform.config import settings


def test_web_search_requires_the_internal_agent_key(
    client: TestClient, api_prefix: str
):
    response = client.post(
        f"{api_prefix}/internal/web-search",
        json={"user_id": "00000000-0000-0000-0000-000000000000", "query": "x"},
    )
    assert response.status_code == 401


def test_web_fetch_without_a_configured_key_explains_what_is_missing(
    client: TestClient,
    register_user,
    api_prefix: str,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "agent_internal_key", "internal-key")
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))
    token = register_user(email="nokey@example.com")["access_token"]
    me = client.get(
        f"{api_prefix}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    response = client.post(
        f"{api_prefix}/internal/web-fetch",
        headers={"X-Agent-Internal-Key": "internal-key"},
        json={"user_id": me["id"], "url": "https://example.org/a"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "provider_not_configured"
    assert "密钥" in response.json()["message"]
