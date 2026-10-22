"""Per-user service credentials survive storage without ever coming back out."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.platform.config import settings


@pytest.fixture(autouse=True)
def master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))


@pytest.fixture
def credential_headers(register_user, client: TestClient) -> dict[str, str]:
    token = register_user()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_stored_api_key_is_ciphertext_in_the_table_and_hidden_from_responses(
    client: TestClient,
    credential_headers: dict[str, str],
    session_factory: sessionmaker,
    api_prefix: str,
    caplog,
) -> None:
    secret = "tvly-test-secret-value"
    saved = client.put(
        f"{api_prefix}/service-credentials/tavily",
        headers=credential_headers,
        json={"kind": "tavily", "label": "我的 Tavily", "fields": {"api_key": secret}},
    )
    assert saved.status_code == 200, saved.text
    assert secret not in saved.text

    listed = client.get(f"{api_prefix}/service-credentials", headers=credential_headers)
    assert listed.status_code == 200
    assert secret not in listed.text
    assert listed.json()["items"][0]["fields"]["api_key"] == "<set>"

    with session_factory() as session:
        stored = session.execute(
            text("SELECT fields FROM service_credentials")
        ).scalar_one()
    assert stored["api_key"].startswith("enc:v1:")
    assert secret not in str(stored)
    assert secret not in caplog.text


def test_saving_the_same_service_again_replaces_the_existing_credentials(
    client: TestClient,
    credential_headers: dict[str, str],
    api_prefix: str,
) -> None:
    for key in ("tvly-first", "tvly-second"):
        response = client.put(
            f"{api_prefix}/service-credentials/tavily",
            headers=credential_headers,
            json={"kind": "tavily", "label": "Tavily", "fields": {"api_key": key}},
        )
        assert response.status_code == 200, response.text

    listed = client.get(f"{api_prefix}/service-credentials", headers=credential_headers)
    assert len(listed.json()["items"]) == 1


def test_another_users_credentials_are_never_visible(
    client: TestClient,
    credential_headers: dict[str, str],
    register_user,
    api_prefix: str,
) -> None:
    client.put(
        f"{api_prefix}/service-credentials/tavily",
        headers=credential_headers,
        json={"kind": "tavily", "label": "Tavily", "fields": {"api_key": "tvly-a"}},
    )
    other = register_user(email="other@example.com")
    listed = client.get(
        f"{api_prefix}/service-credentials",
        headers={"Authorization": f"Bearer {other['access_token']}"},
    )
    assert listed.json()["items"] == []


def test_agent_secret_lookup_returns_the_decrypted_key(
    client: TestClient,
    credential_headers: dict[str, str],
    register_user,
    api_prefix: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "internal-key")
    me = client.get(f"{api_prefix}/auth/me", headers=credential_headers)
    user_id = me.json()["id"]
    client.put(
        f"{api_prefix}/service-credentials/tavily",
        headers=credential_headers,
        json={"kind": "tavily", "label": "Tavily", "fields": {"api_key": "tvly-real"}},
    )

    response = client.post(
        f"{api_prefix}/internal/service-credentials/secret",
        headers={"X-Agent-Internal-Key": "internal-key"},
        json={"user_id": user_id, "kind": "tavily", "field": "api_key"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"value": "tvly-real"}


def test_missing_credential_reports_a_configuration_error(
    client: TestClient,
    register_user,
    api_prefix: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "internal-key")
    registered = register_user(email="unset@example.com")
    me = client.get(
        f"{api_prefix}/auth/me",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )
    response = client.post(
        f"{api_prefix}/internal/service-credentials/secret",
        headers={"X-Agent-Internal-Key": "internal-key"},
        json={"user_id": me.json()["id"], "kind": "tavily", "field": "api_key"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "provider_not_configured"
