"""Shared pytest fixtures.

Integration tests run against a real PostgreSQL + pgvector database because the
schema depends on JSONB, full-text search and vector types. The test database is
created on demand, migrated with Alembic and truncated between tests.
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.main import create_app
from app.platform.config import settings
from app.platform.database import get_session, get_session_factory
from app.platform.storage import LocalObjectStorage, get_object_storage
from app.platform.tasks import InlineTaskScheduler, get_task_scheduler

BACKEND_ROOT = Path(__file__).resolve().parent.parent

SessionFactory = Callable[[], Session]


def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    database = parsed.database
    if not database:
        raise RuntimeError("测试数据库 URL 缺少数据库名")
    admin_url = parsed.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{database}"'))
    finally:
        admin_engine.dispose()


def _run_migrations(url: str) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = settings.resolved_test_database_url
    _ensure_database(url)
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    _run_migrations(url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(engine: Engine) -> Iterator[None]:
    yield
    tables = [
        name
        for name in inspect(engine).get_table_names(schema="public")
        if name != "alembic_version"
    ]
    if not tables:
        return
    quoted = ", ".join(f'"{name}"' for name in tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    root = tmp_path / "storage"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    storage_root: Path,
) -> Iterator[TestClient]:
    app = create_app()
    storage = LocalObjectStorage(storage_root)

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_task_scheduler] = InlineTaskScheduler
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def api_prefix() -> str:
    return settings.api_prefix


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def register_user(client: TestClient, api_prefix: str) -> Callable[..., dict]:
    """Register a user and return the parsed session payload."""

    def _register(
        email: str = "reader@example.com",
        password: str = "correct-horse-battery",
        display_name: str = "Reader",
    ) -> dict:
        response = client.post(
            f"{api_prefix}/auth/register",
            json={
                "email": email,
                "password": password,
                "display_name": display_name,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _register


os.environ.setdefault("TZ", "UTC")
