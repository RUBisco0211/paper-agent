"""Credential encryption and response boundaries on real AgentScope SQL storage."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from agent_service.credential_storage import EncryptedCredentialStorage
from agent_service.main import create_agent_service_app
from app.platform.config import settings
from tests.agent_service.test_auth import _scope_database_url


def test_credential_key_is_encrypted_in_sql_and_absent_from_list_response(
    tmp_path: Path, monkeypatch, agent_access_token, caplog
) -> None:
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    token = agent_access_token
    headers = {"Authorization": f"Bearer {token}"}
    fake_key = "sk-test-credential-secret"
    with TestClient(app) as client:
        created = client.post(
            "/credential/",
            headers=headers,
            json={
                "data": {
                    "type": "openai_credential",
                    "name": "Personal OpenAI",
                    "api_key": fake_key,
                },
            },
        )
        assert created.status_code == 201, created.text
        credential_id = created.json()["credential_id"]
        listed = client.get("/credential/", headers=headers)
        assert listed.status_code == 200
        assert fake_key not in listed.text

    engine = create_engine(_scope_database_url())
    try:
        with engine.connect() as connection:
            payload = connection.execute(
                text("SELECT payload FROM credentials WHERE id = :credential_id"),
                {"credential_id": credential_id},
            ).scalar_one()
    finally:
        engine.dispose()
    assert payload["data"]["api_key"].startswith("enc:v1:")
    assert fake_key not in str(payload)
    assert fake_key not in caplog.text


def test_credential_cannot_target_a_browser_supplied_base_url(
    tmp_path: Path, monkeypatch, agent_access_token
) -> None:
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    token = agent_access_token
    with TestClient(app) as client:
        response = client.post(
            "/credential/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "data": {
                    "type": "openai_credential",
                    "name": "Unsafe",
                    "api_key": "sk-test",
                    "base_url": "http://127.0.0.1:9/v1",
                },
            },
        )
    assert response.status_code == 422


def test_credential_uses_the_registered_base_url_when_browser_omits_it(
    tmp_path: Path, monkeypatch, agent_access_token
) -> None:
    registered_url = "https://llm.example.test/v1"
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))
    monkeypatch.setattr(settings, "credential_base_urls", {"openai": registered_url})
    token = agent_access_token
    with TestClient(
        create_agent_service_app(_scope_database_url(), tmp_path)
    ) as client:
        response = client.post(
            "/credential/",
            headers={"Authorization": f"Bearer {token}"},
            json={"data": {"type": "openai_credential", "api_key": "sk-fake-key"}},
        )
        assert response.status_code == 201, response.text
        listed = client.get(
            "/credential/", headers={"Authorization": f"Bearer {token}"}
        ).json()["credentials"]

    assert listed[0]["data"]["base_url"] == registered_url


def test_credential_uses_the_registered_base_url_when_browser_sends_null(
    tmp_path: Path, monkeypatch, agent_access_token
) -> None:
    registered_url = "https://llm.example.test/v1"
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))
    monkeypatch.setattr(settings, "credential_base_urls", {"openai": registered_url})
    with TestClient(
        create_agent_service_app(_scope_database_url(), tmp_path)
    ) as client:
        headers = {"Authorization": f"Bearer {agent_access_token}"}
        response = client.post(
            "/credential/",
            headers=headers,
            json={
                "data": {
                    "type": "openai_credential",
                    "api_key": "sk-fake-key",
                    "base_url": None,
                }
            },
        )
        assert response.status_code == 201, response.text
        listed = client.get("/credential/", headers=headers).json()["credentials"]

    assert listed[0]["data"]["base_url"] == registered_url


def test_credential_update_response_never_returns_the_key(
    tmp_path: Path, monkeypatch, agent_access_token
) -> None:
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    token = agent_access_token
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        created = client.post(
            "/credential/",
            headers=headers,
            json={
                "data": {
                    "type": "openai_credential",
                    "api_key": "sk-first-fake-key",
                }
            },
        )
        assert created.status_code == 201
        updated = client.patch(
            f"/credential/{created.json()['credential_id']}",
            headers=headers,
            json={
                "data": {
                    "type": "openai_credential",
                    "api_key": "sk-second-fake-key",
                }
            },
        )

    assert updated.status_code == 200, updated.text
    assert "sk-second-fake-key" not in updated.text


def test_credential_storage_refuses_a_different_master_key_after_restart(
    tmp_path: Path, monkeypatch, agent_access_token
) -> None:
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))
    database_url = _scope_database_url()
    token = agent_access_token
    with TestClient(create_agent_service_app(database_url, tmp_path)) as client:
        created = client.post(
            "/credential/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "data": {
                    "type": "openai_credential",
                    "api_key": "sk-restart-fake-key",
                }
            },
        )
        assert created.status_code == 201

    monkeypatch.setattr(settings, "credential_master_key", SecretStr("c" * 64))
    with (
        pytest.raises(RuntimeError, match="credential_decryption_failed"),
        TestClient(create_agent_service_app(database_url, tmp_path)),
    ):
        pass


def test_agent_service_refuses_to_start_without_credential_master_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "credential_master_key", SecretStr(""))
    with (
        pytest.raises(RuntimeError, match="CREDENTIAL_MASTER_KEY"),
        TestClient(create_agent_service_app(_scope_database_url(), tmp_path)),
    ):
        pass


def test_user_derived_key_rejects_cross_user_or_tampered_ciphertext() -> None:
    storage = EncryptedCredentialStorage(
        "postgresql+asyncpg://unused/unused",
        key_provider=lambda: "a" * 64,
    )
    storage._master_key = bytes.fromhex("a" * 64)
    owner, stranger, credential_id = str(uuid4()), str(uuid4()), uuid4().hex
    ciphertext = storage._encrypt(owner, credential_id, "sk-fake-key")

    assert storage._decrypt(owner, credential_id, ciphertext) == "sk-fake-key"
    with pytest.raises(RuntimeError, match="credential_decryption_failed"):
        storage._decrypt(stranger, credential_id, ciphertext)
    with pytest.raises(RuntimeError, match="credential_decryption_failed"):
        storage._decrypt(owner, uuid4().hex, ciphertext)
    with pytest.raises(RuntimeError, match="credential_decryption_failed"):
        storage._decrypt(owner, credential_id, ciphertext[:-3] + "AAA")
