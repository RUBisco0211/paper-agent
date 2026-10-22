"""Search the public web and read pages on one user's behalf."""

from uuid import UUID

import structlog

from ..platform.errors import (
    AppError,
    ErrorCode,
    ProviderNotConfiguredError,
    ProviderUnavailableError,
    RateLimitedError,
)
from .domain import (
    DEFAULT_MAX_CHARS,
    MAX_MAX_CHARS,
    InvalidCredential,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderUnavailable,
    WebPageNotFound,
    search_envelope,
    window_page,
)
from .page_cache import PageCacheUnavailable
from .ports import CredentialReader, PageStore, ProviderFactory

logger = structlog.get_logger(__name__)

PROVIDER_KIND = "tavily"
DEFAULT_PROVIDER_NAME = "tavily"


class InvalidWebCredentialError(ProviderNotConfiguredError):
    """The stored key exists but the provider rejected it."""

    message = "联网搜索密钥无效或已被吊销，请在设置中重新填写"


class WebSearchService:
    def __init__(
        self,
        credentials: CredentialReader,
        pages: PageStore,
        provider_factory: ProviderFactory,
    ) -> None:
        self._credentials = credentials
        self._pages = pages
        self._provider_factory = provider_factory

    def search(self, user_id: UUID, query: str, max_results: int) -> dict:
        provider = self._provider_for(user_id)
        try:
            results = provider.search(query, max_results)
        except Exception as exc:
            failure = self._translate(exc, "联网搜索")
            raise failure from exc
        return search_envelope(DEFAULT_PROVIDER_NAME, results)

    def fetch(self, user_id: UUID, url: str, offset: int, max_chars: int) -> dict:
        size = max(1, min(max_chars, MAX_MAX_CHARS))
        content = self._cached(user_id, url)
        if content is None:
            provider = self._provider_for(user_id)
            try:
                content = provider.extract(url)
            except Exception as exc:
                failure = self._translate(exc, "网页读取")
                raise failure from exc
            self._remember(user_id, url, content)
        return window_page(url, content, max(0, offset), size)

    def excerpt(self, user_id: UUID, url: str, query: str, chunks: int) -> dict:
        provider = self._provider_for(user_id)
        try:
            content = provider.extract_excerpt(url, query, chunks)
        except Exception as exc:
            failure = self._translate(exc, "网页读取")
            raise failure from exc
        return {
            "status": "ok",
            "url": url,
            "content": content,
            "excerpt_only": True,
        }

    def _provider_for(self, user_id: UUID):
        api_key = self._credentials.secret(user_id, PROVIDER_KIND, "api_key")
        if api_key is None:
            raise ProviderNotConfiguredError()
        return self._provider_factory(api_key)

    def _cached(self, user_id: UUID, url: str) -> str | None:
        """A cache miss and a broken cache are the same thing here: fetch again."""
        try:
            return self._pages.get(str(user_id), url)
        except PageCacheUnavailable:
            return None

    def _remember(self, user_id: UUID, url: str, content: str) -> None:
        """Failing to cache costs one extra fetch later; it must not fail the read."""
        try:
            self._pages.put(str(user_id), url, content)
        except PageCacheUnavailable:
            return

    @staticmethod
    def _translate(exc: Exception, label: str) -> AppError:
        if isinstance(exc, InvalidCredential):
            return InvalidWebCredentialError()
        if isinstance(exc, ProviderRateLimited):
            return RateLimitedError(f"{label}触发服务方限流，请稍后重试")
        if isinstance(exc, ProviderQuotaExhausted):
            return ProviderUnavailableError(
                f"{label}额度已用尽，请检查账户额度",
                code=ErrorCode.PROVIDER_QUOTA_EXHAUSTED,
            )
        if isinstance(exc, WebPageNotFound):
            return ProviderUnavailableError("该页面无法读取，可能已失效或不允许抓取")
        if isinstance(exc, ProviderUnavailable):
            return ProviderUnavailableError(f"{label}暂时不可用")
        # A configuration fault inside the provider call is not an outage, but it
        # is also not something the user can act on. Keep the type for diagnosis
        # without exposing internals, and never let a bare 500 reach the caller.
        logger.warning(
            "web.unexpected_provider_error",
            error=type(exc).__name__,
            label=label,
        )
        return ProviderUnavailableError(
            f"{label}暂时不可用",
            details={"error": type(exc).__name__},
        )


__all__ = ["DEFAULT_MAX_CHARS", "InvalidWebCredentialError", "WebSearchService"]
