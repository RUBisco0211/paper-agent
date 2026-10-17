"""JWT ownership and browser access for the AgentScope service."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from agent_service.main import create_agent_service_app
from app.platform.config import settings
from app.platform.security import create_access_token


def _scope_database_url() -> str:
    url = make_url(settings.resolved_test_database_url).set(
        database="paper_agent_scope_test",
    )
    admin_engine = create_engine(url.set(database="postgres"))
    try:
        with admin_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT",
        ) as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar()
            if not exists:
                connection.execute(text('CREATE DATABASE "paper_agent_scope_test"'))
    finally:
        admin_engine.dispose()
    return url.render_as_string(hide_password=False)


def test_agent_service_rejects_untrusted_identity_when_token_is_missing_or_expired(
    tmp_path: Path,
) -> None:
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    expired, _ = create_access_token(
        user_id=uuid4(),
        auth_session_id=uuid4(),
        now=datetime.now(UTC) - timedelta(minutes=16),
    )
    with TestClient(app) as client:
        assert client.get("/agent/").status_code == 401
        assert client.get("/agent/", headers={"X-User-ID": "forged"}).status_code == 401
        assert (
            client.get(
                "/agent/",
                headers={"Authorization": f"Bearer {expired}"},
            ).status_code
            == 401
        )


def test_agent_service_uses_bearer_identity_and_allows_browser_origin(
    tmp_path: Path,
    client: TestClient,
    api_prefix: str,
    register_user,
    agent_business_http,
) -> None:
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    registered = register_user(email="agent-service-user@example.com")
    first = registered["access_token"]
    business_user_id = registered["user"]["id"]
    second = register_user(email="other-agent-user@example.com")["access_token"]
    origin = settings.cors_origins[0]
    with TestClient(app) as client:
        preflight = client.options(
            "/agent/",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin

        created = client.post(
            "/agent/",
            json={"name": "Private Reader"},
            headers={"Authorization": f"Bearer {first}", "Origin": origin},
        )
        assert created.status_code == 201
        assert created.headers["access-control-allow-origin"] == origin
        first_agents = client.get(
            "/agent/",
            headers={"Authorization": f"Bearer {first}"},
        ).json()["agents"]
        second_agents = client.get(
            "/agent/",
            headers={"Authorization": f"Bearer {second}"},
        ).json()["agents"]
        assert any(view["id"] == created.json()["agent_id"] for view in first_agents)
        assert first_agents[0]["user_id"] == business_user_id
        assert second_agents == []


def test_agent_service_rejects_existing_bearer_when_business_session_is_revoked(
    tmp_path,
    client,
    register_user,
    agent_business_http,
):
    owner = register_user()
    app = create_agent_service_app(_scope_database_url(), tmp_path)
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    with TestClient(app) as agent_client:
        assert agent_client.get("/agent/", headers=headers).status_code == 200
        assert client.post("/v1/auth/logout").status_code == 204
        assert agent_client.get("/agent/", headers=headers).status_code == 401
