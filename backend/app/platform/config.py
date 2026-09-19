from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: 已知的占位符/示例密钥：出现在生产配置里意味着令牌可被伪造
PLACEHOLDER_JWT_SECRET = "replace-with-openssl-rand-hex-32"
KNOWN_WEAK_JWT_SECRETS = frozenset(
    {
        PLACEHOLDER_JWT_SECRET,
        "change-me",
        "change-me-please-set-a-real-secret",
        "secret",
        "jwt-secret",
    },
)
#: HS256 的密钥长度下限（32 字节 = 256 bit）
MIN_JWT_SECRET_CHARS = 32


class Settings(BaseSettings):
    """Instance-level configuration.

    Everything here is fixed by the deployer through environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Paper Agent API"
    app_version: str = "0.1.0"
    api_prefix: str = "/v1"
    environment: str = "development"

    # Database
    database_url: str = (
        "postgresql+psycopg://paper_agent:paper_agent_dev@127.0.0.1:5432/paper_agent"
    )
    test_database_url: str | None = None
    database_echo: bool = False

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    # Browser clients allowed to call the API with credentials.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Object storage (PDF, MinerU artifacts, session entry logs)
    storage_root: Path = Path(".var/storage")
    #: local | s3；s3 指任何 S3 兼容服务（RustFS / Garage / 云对象存储）
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "paper-agent"
    s3_region: str = "us-east-1"
    #: 自建服务通常只支持 path-style（bucket 放在路径里）
    s3_addressing_style: str = "path"

    # Upload limits
    max_pdf_bytes: int = 50 * 1024 * 1024
    max_pdf_pages: int = 300

    # Authentication
    #: 必须在部署环境里换成随机值，例如 `openssl rand -hex 32`。
    #: 占位符与弱值会让令牌可被伪造，启动时会检查（见 app/main.py）。
    jwt_secret_key: str = PLACEHOLDER_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    refresh_cookie_name: str = "paper_agent_refresh"
    refresh_cookie_secure: bool = False
    refresh_cookie_domain: str | None = None

    # Instance-level providers
    mineru_api_url: str | None = None
    mineru_api_key: str | None = None
    mineru_timeout_seconds: float = 600.0
    embedding_api_url: str | None = None
    embedding_api_key: str | None = None
    # 默认按 BAAI/bge-m3：1024 维、8192 上下文、无需 query/document 前缀。
    # 维度必须与 alembic 迁移里 chunks.embedding 的维度一致。
    embedding_adapter: str = "openai_compatible"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    # 留空则用模型档案里的默认值（见 retrieval/embedding/profiles.py）
    embedding_max_input_chars: int | None = None
    embedding_max_batch_items: int | None = None
    embedding_max_batch_chars: int | None = None
    embedding_query_prefix: str | None = None
    embedding_document_prefix: str | None = None
    crossref_api_url: str = "https://api.crossref.org"
    arxiv_api_url: str = "https://export.arxiv.org/api/query"
    arxiv_pdf_url: str = "https://arxiv.org/pdf"
    zotero_recognizer_url: str | None = None
    outbound_timeout_seconds: float = 20.0

    # Provider/model choices come from AgentScope model cards. Users may select
    # from this allow-list and supply a key, but cannot enter arbitrary names or URLs.
    llm_providers: list[str] = [
        "openai",
        "anthropic",
        "dashscope",
        "deepseek",
        "moonshot",
        "xai",
    ]

    # Retrieval
    keyword_top_n: int = 20
    vector_top_n: int = 20
    rrf_k: int = 60
    max_evidence_chunks: int = 12
    max_evidence_per_paper: int = 4

    # Chunking
    chunk_token_num: int = 512
    chunk_max_chars: int = 4000

    # Agent 回合
    agent_max_iters: int = 8
    agent_turn_timeout_seconds: float = 240.0

    # Sessions
    session_idle_flush_seconds: int = 300
    session_event_buffer_size: int = 500
    # An idle SSE subscription is closed after this long; clients reconnect
    # with their cursor, which keeps reconnects cheap and stateless.
    sse_idle_timeout_seconds: float = 60.0

    @property
    def jwt_secret_problem(self) -> str | None:
        """返回密钥的问题码；None 表示可用。"""
        secret = self.jwt_secret_key or ""
        if not secret or secret in KNOWN_WEAK_JWT_SECRETS:
            return "placeholder"
        if len(secret) < MIN_JWT_SECRET_CHARS:
            return "too_short"
        if len(set(secret)) < 8:
            return "low_entropy"
        return None

    @property
    def resolved_test_database_url(self) -> str:
        """Database used by integration tests.

        Falls back to the configured database with a `_test` suffix so tests
        never touch development data.
        """
        if self.test_database_url:
            return self.test_database_url
        head, _, _tail = self.database_url.rpartition("/")
        return f"{head}/paper_agent_test"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
