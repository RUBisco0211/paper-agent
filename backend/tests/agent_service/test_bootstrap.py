"""AgentScope service integration tests against PostgreSQL."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from agent_service.main import create_agent_service_app
from app.platform.config import settings


def test_new_sessions_have_distinct_internal_workspaces_when_they_share_an_agent(
    tmp_path: Path,
    agent_access_token,
) -> None:
    database_url = make_url(settings.resolved_test_database_url).set(
        database="paper_agent_scope_test",
    )
    admin_engine = create_engine(database_url.set(database="postgres"))
    try:
        with admin_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT",
        ) as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_url.database},
            ).scalar()
            if not exists:
                connection.execute(text('CREATE DATABASE "paper_agent_scope_test"'))
    finally:
        admin_engine.dispose()

    app = create_agent_service_app(
        database_url.render_as_string(hide_password=False),
        tmp_path,
    )
    headers = {"Authorization": f"Bearer {agent_access_token}"}
    with TestClient(app) as client:
        agent = client.post("/agent/", json={"name": "Reader"}, headers=headers)
        assert agent.status_code == 201
        agent_id = agent.json()["agent_id"]
        first = client.post(
            "/sessions/",
            json={"agent_id": agent_id},
            headers=headers,
        )
        second = client.post(
            "/sessions/",
            json={"agent_id": agent_id},
            headers=headers,
        )
        assert first.status_code == second.status_code == 201
        sessions = client.get(
            "/sessions/",
            params={"agent_id": agent_id},
            headers=headers,
        ).json()["sessions"]
        workspaces = {
            view["session"]["id"]: view["session"]["config"]["workspace_id"]
            for view in sessions
        }
        assert (
            workspaces[first.json()["session_id"]]
            != workspaces[second.json()["session_id"]]
        )


def test_agent_service_preserves_sessions_when_the_process_restarts(
    tmp_path: Path,
    agent_access_token,
) -> None:
    database_url = make_url(settings.resolved_test_database_url).set(
        database="paper_agent_scope_test",
    )
    admin_engine = create_engine(database_url.set(database="postgres"))
    try:
        with admin_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT",
        ) as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_url.database},
            ).scalar()
            if not exists:
                connection.execute(text('CREATE DATABASE "paper_agent_scope_test"'))
    finally:
        admin_engine.dispose()

    service_url = database_url.render_as_string(hide_password=False)
    app = create_agent_service_app(service_url, tmp_path)
    headers = {"Authorization": f"Bearer {agent_access_token}"}
    with TestClient(app) as client:
        assert client.get("/health", headers=headers).json()["status"] == "ok"
        agent = client.post("/agent/", json={"name": "Reader"}, headers=headers)
        assert agent.status_code == 201
        session = client.post(
            "/sessions/",
            json={"agent_id": agent.json()["agent_id"], "name": "Persistent"},
            headers=headers,
        )
        assert session.status_code == 201
        session_id = session.json()["session_id"]

    restarted = create_agent_service_app(service_url, tmp_path)
    with TestClient(restarted) as client:
        response = client.get(
            "/sessions/",
            params={"agent_id": agent.json()["agent_id"]},
            headers=headers,
        )
        assert response.status_code == 200
        matching = [
            view["session"]
            for view in response.json()["sessions"]
            if view["session"]["id"] == session_id
        ]
        assert matching[0]["config"]["name"] == "Persistent"
