"""Per-user tool approval settings never apply to another account."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from alembic import command
from app.auth.repo import AuthRepository
from app.platform.config import settings
from tests.conftest import auth_headers


def test_tool_approval_setting_is_private_and_defaults_to_review(
    client: TestClient, api_prefix: str, register_user
):
    first = register_user(email="first@example.com")
    second = register_user(email="second@example.com")
    path = f"{api_prefix}/auth/tool-authorizations"

    assert client.get(path, headers=auth_headers(first["access_token"])).json() == {
        "import_selected_papers": False,
        "create_scheduled_task": False,
    }
    updated = client.patch(
        f"{path}/create_scheduled_task",
        headers=auth_headers(first["access_token"]),
        json={"always_allow": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["always_allow"] is True
    assert (
        client.get(path, headers=auth_headers(second["access_token"])).json()[
            "create_scheduled_task"
        ]
        is False
    )
    internal = client.get(
        f"{api_prefix}/internal/tool-authorizations",
        params={"user_id": first["user"]["id"]},
        headers={"X-Agent-Internal-Key": settings.agent_internal_key},
    )
    assert internal.json()["create_scheduled_task"] is True


def test_user_settings_preserve_other_json_when_tool_policy_changes(
    client: TestClient, api_prefix: str, register_user, engine: Engine
):
    user = register_user(email="settings@example.com")
    user_id = user["user"]["id"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO user_settings (user_id, config) "
                "VALUES (:user_id, CAST(:config AS jsonb))"
            ),
            {
                "user_id": user_id,
                "config": '{"version":1,"appearance":{"theme":"dark"}}',
            },
        )

    path = f"{api_prefix}/auth/tool-authorizations"
    for tool_name in ("create_scheduled_task", "import_selected_papers"):
        response = client.patch(
            f"{path}/{tool_name}",
            headers=auth_headers(user["access_token"]),
            json={"always_allow": True},
        )
        assert response.status_code == 200, response.text

    with engine.connect() as connection:
        config = connection.execute(
            text("SELECT config FROM user_settings WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).scalar_one()
    assert config == {
        "version": 1,
        "appearance": {"theme": "dark"},
        "agent_tools": {
            "always_allow": {
                "create_scheduled_task": True,
                "import_selected_papers": True,
            }
        },
    }
    assert "user_tool_authorizations" not in inspect(engine).get_table_names()


def test_concurrent_tool_settings_updates_preserve_both_values(
    client: TestClient, register_user, engine: Engine
):
    user_id = UUID(register_user(email="concurrent@example.com")["user"]["id"])
    barrier = Barrier(2)

    def update(tool_name: str) -> None:
        with Session(engine) as session:
            repository = AuthRepository(session)
            barrier.wait(timeout=5)
            repository.set_tool_authorization(user_id, tool_name, True)
            repository.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            pool.submit(update, name)
            for name in ("create_scheduled_task", "import_selected_papers")
        ]
        for result in results:
            result.result(timeout=10)

    with engine.connect() as connection:
        config = connection.execute(
            text("SELECT config FROM user_settings WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).scalar_one()
    assert config["agent_tools"]["always_allow"] == {
        "create_scheduled_task": True,
        "import_selected_papers": True,
    }


def test_user_settings_migration_preserves_existing_tool_choices(
    client: TestClient, register_user, engine: Engine
):
    user_id = UUID(register_user(email="migration@example.com")["user"]["id"])
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False)
    )
    command.downgrade(config, "20261010_0017")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO user_tool_authorizations "
                    "(id, user_id, tool_name, always_allow) "
                    "VALUES (gen_random_uuid(), :user_id, :tool_name, :always_allow)"
                ),
                [
                    {
                        "user_id": user_id,
                        "tool_name": "create_scheduled_task",
                        "always_allow": True,
                    },
                    {
                        "user_id": user_id,
                        "tool_name": "import_selected_papers",
                        "always_allow": False,
                    },
                ],
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            settings = connection.execute(
                text("SELECT config FROM user_settings WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).scalar_one()
        assert settings["agent_tools"]["always_allow"] == {
            "create_scheduled_task": True,
            "import_selected_papers": False,
        }
    finally:
        command.upgrade(config, "head")


def test_timezone_setting_is_validated_and_private(
    client: TestClient, api_prefix: str, register_user, engine: Engine
):
    first = register_user(email="first-zone@example.com")
    second = register_user(email="second-zone@example.com")
    path = f"{api_prefix}/auth/timezone"
    bad = client.patch(
        path,
        headers=auth_headers(first["access_token"]),
        json={"timezone": "Not/AZone"},
    )
    assert bad.status_code == 422
    saved = client.patch(
        path,
        headers=auth_headers(first["access_token"]),
        json={"timezone": "Europe/Berlin"},
    )
    assert saved.status_code == 200
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT user_id, config FROM user_settings ORDER BY user_id")
        ).all()
    assert len(rows) == 1
    assert str(rows[0].user_id) == first["user"]["id"]
    assert rows[0].config["timezone"] == "Europe/Berlin"
    assert str(rows[0].user_id) != second["user"]["id"]
