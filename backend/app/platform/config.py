from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Instance-level configuration.

    Everything here is fixed by the deployer through environment variables.
    Per-user configuration (LLM provider, model, API key) never lives here.
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
        "postgresql+psycopg://paper_agent:change-me@127.0.0.1:5432/paper_agent"
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

    # Upload limits
    max_pdf_bytes: int = 50 * 1024 * 1024
    max_pdf_pages: int = 300

    # Authentication
    jwt_secret_key: str = "change-me-please-set-a-real-secret"
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
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    crossref_api_url: str = "https://api.crossref.org"
    arxiv_api_url: str = "https://export.arxiv.org/api/query"
    arxiv_pdf_url: str = "https://arxiv.org/pdf"
    zotero_recognizer_url: str | None = None
    outbound_timeout_seconds: float = 20.0

    # Allowed LLM providers mapped to their fixed base URL. Users pick a
    # provider and a model from this list; they can never supply a base URL.
    llm_providers: dict[str, str] = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
    }

    # Retrieval
    keyword_top_n: int = 20
    vector_top_n: int = 20
    rrf_k: int = 60
    max_evidence_chunks: int = 12
    max_evidence_per_paper: int = 4

    # Chunking
    chunk_token_num: int = 512
    chunk_max_chars: int = 4000

    # Sessions
    session_idle_flush_seconds: int = 300
    session_event_buffer_size: int = 500

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
