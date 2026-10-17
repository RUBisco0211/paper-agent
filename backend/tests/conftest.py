"""Shared pytest fixtures.

Integration tests run against a real PostgreSQL + pgvector database because the
schema depends on JSONB, full-text search and vector types. The test database is
created on demand, migrated with Alembic and truncated between tests.
"""

import io
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import uuid4

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
from app.platform.storage import (
    LocalObjectStorage,
    ObjectStorage,
    get_object_storage,
)
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


@pytest.fixture(autouse=True, scope="session")
def isolated_provider_config() -> Iterator[None]:
    """测试默认不依赖开发者 .env 里的 Provider 配置。

    本地填了真实 MinerU/Embedding 凭据时，用例会去调用外部服务，结果随环境而变。
    想用真实服务跑测试时设置 ``PAPER_AGENT_LIVE_PROVIDERS=1``；验证真实链路更推荐
    backend/README 里的手工方式（上传真实 PDF 观察阶段与检索）。
    """
    if os.environ.get("PAPER_AGENT_LIVE_PROVIDERS") == "1":
        yield
        return
    provider_settings = [
        "mineru_api_url",
        "mineru_api_key",
        "embedding_api_url",
        "embedding_api_key",
        "zotero_recognizer_url",
    ]
    original = {name: getattr(settings, name) for name in provider_settings}
    for name in provider_settings:
        setattr(settings, name, None)
    yield
    for name, value in original.items():
        setattr(settings, name, value)


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


def _truncate_all(engine: Engine) -> None:
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
def clean_tables(engine: Engine) -> None:
    """按需清库：只有真正用到数据库的用例才触发连接。

    这样纯单元测试（分块、RRF、适配器）不需要 Postgres 也能跑。
    """
    # Truncate before each test so a killed run can never leak state into the
    # next one.
    _truncate_all(engine)


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(
    session_factory: sessionmaker[Session],
    clean_tables: None,
) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    root = tmp_path / "storage"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def storage(storage_root: Path) -> Iterator[ObjectStorage]:
    """应用使用的存储。

    默认是临时目录；设 ``PAPER_AGENT_LIVE_STORAGE=1`` 时改用 ``backend/.env``
    里配置的真实 S3 兼容服务（如本地 RustFS），用后清理，便于整套 API 级用例
    直接跑在对象存储上。
    """
    if os.environ.get("PAPER_AGENT_LIVE_STORAGE") != "1":
        yield LocalObjectStorage(storage_root)
        return
    from app.platform.s3_storage import S3ObjectStorage

    live = S3ObjectStorage(
        bucket=f"{settings.s3_bucket}-live-test",
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
        addressing_style=settings.s3_addressing_style,
    )
    try:
        yield live
    finally:
        for prefix in ("papers/", "mineru/", "sessions/"):
            live.delete_prefix(prefix)


@pytest.fixture(scope="session")
def auth_redis(tmp_path_factory):
    from redis import Redis
    from redis.exceptions import ConnectionError

    url = os.environ.get("PAPER_AGENT_TEST_REDIS_URL")
    if url:
        with Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3) as redis:
            redis.ping()
            yield redis
        return

    executable = shutil.which("redis-server")
    if executable is None:
        raise RuntimeError("Auth integration tests require redis-server")
    root = tmp_path_factory.mktemp("auth-redis")
    socket_dir = tempfile.TemporaryDirectory(prefix="auth-redis-", dir="/tmp")
    socket = Path(socket_dir.name) / "redis.sock"
    process = subprocess.Popen(
        [
            executable,
            "--port",
            "0",
            "--unixsocket",
            str(socket),
            "--save",
            "",
            "--appendonly",
            "no",
            "--dir",
            str(root),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    redis = Redis(unix_socket_path=str(socket), socket_timeout=3)
    try:
        for _ in range(100):
            try:
                if redis.ping():
                    break
            except ConnectionError as exc:
                if process.poll() is not None:
                    raise RuntimeError(
                        "Test Redis exited before becoming ready"
                    ) from exc
                time.sleep(0.05)
        else:
            raise RuntimeError("Test Redis did not become ready")
        yield redis
    finally:
        redis.close()
        process.terminate()
        process.wait(timeout=5)
        socket_dir.cleanup()


@pytest.fixture
def email_verification_store(auth_redis, monkeypatch):
    from app.auth.repo import EmailVerificationStore

    # Contract settings are supplied by the parallel integration task.
    for name, value in [
        ("email_verification_ttl_seconds", 600),
        ("email_resend_cooldown_seconds", 60),
        ("email_verification_max_attempts", 5),
    ]:
        if not hasattr(settings, name):
            monkeypatch.setattr(type(settings), name, value, raising=False)
    store = EmailVerificationStore(
        auth_redis,
        secret="isolated-test-email-secret",
        namespace="test-auth:{" + uuid4().hex + "}",
    )
    yield store
    keys = list(auth_redis.scan_iter(match=store.namespace + ":*"))
    if keys:
        auth_redis.delete(*keys)


@pytest.fixture
def auth_emails(monkeypatch):
    from app.auth.repo import AuthRepository

    messages = []

    def enqueue_verification(repository, **message):
        messages.append(dict(kind="verification", **message))

    def enqueue_reset(repository, **message):
        messages.append(dict(kind="password_reset", **message))

    monkeypatch.setattr(
        AuthRepository, "enqueue_verification_email", enqueue_verification
    )
    monkeypatch.setattr(AuthRepository, "enqueue_password_reset_email", enqueue_reset)
    return messages


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
    clean_tables: None,
    email_verification_store,
    auth_emails,
) -> Iterator[TestClient]:
    app = create_app()
    from app.auth.depends import get_email_verification_store

    app.dependency_overrides[get_email_verification_store] = lambda: (
        email_verification_store
    )

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


def build_pdf_with_text(text: str) -> bytes:
    """Build a one-page PDF whose text layer contains ``text``.

    Written by hand because the tests need extractable text, not just pages.
    """
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    content = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(out)


@pytest.fixture
def make_pdf() -> Callable[..., bytes]:
    """Build a small, valid, born-digital PDF for upload tests."""

    def _make_pdf(page_count: int = 1) -> bytes:
        from pypdf import PdfWriter

        writer = PdfWriter()
        for _ in range(page_count):
            writer.add_blank_page(width=612, height=792)
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    return _make_pdf


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def register_user(
    client: TestClient, api_prefix: str, auth_emails
) -> Callable[..., dict]:
    """Register a user and return the parsed session payload."""

    def _register(
        email: str = "reader@example.com",
        password: str = "correct-horse-battery",
        display_name: str = "Reader",
    ) -> dict:
        requested = client.post(
            f"{api_prefix}/auth/email-codes",
            json={"email": email, "purpose": "register"},
        )
        assert requested.status_code == 200, requested.text
        verified = client.post(
            f"{api_prefix}/auth/email-codes/verify",
            json={
                "challenge_id": requested.json()["challenge_id"],
                "code": auth_emails[-1]["code"],
                "purpose": "register",
            },
        )
        assert verified.status_code == 200, verified.text
        response = client.post(
            f"{api_prefix}/auth/register",
            json={
                "verification_token": verified.json()["verification_token"],
                "password": password,
                "password_confirmation": password,
                "display_name": display_name,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _register


os.environ.setdefault("TZ", "UTC")
