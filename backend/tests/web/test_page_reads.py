"""Page reads are windowed, cached per user, and never leak across users."""

from uuid import uuid4

import pytest

from app.web.domain import (
    InvalidCredential,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderUnavailable,
    WebPageNotFound,
)
from app.web.page_cache import PageCacheUnavailable, WebPageCache
from app.web.service import InvalidWebCredentialError, WebSearchService


class FakeProvider:
    def __init__(self, body: str = "abcdefghij", error: Exception | None = None):
        self.body = body
        self.error = error
        self.extract_calls = 0

    def search(self, query: str, max_results: int) -> list[dict]:
        if self.error:
            raise self.error
        return [{"title": "t", "url": "https://a", "snippet": "s"}]

    def extract(self, url: str) -> str:
        self.extract_calls += 1
        if self.error:
            raise self.error
        return self.body

    def extract_excerpt(self, url: str, query: str, chunks: int) -> str:
        if self.error:
            raise self.error
        return "passage"


class DictStore:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}

    def get(self, user_id: str, url: str) -> str | None:
        return self.items.get((user_id, url))

    def put(self, user_id: str, url: str, content: str) -> None:
        self.items[(user_id, url)] = content


class FailingStore:
    def get(self, user_id: str, url: str) -> str | None:
        raise PageCacheUnavailable

    def put(self, user_id: str, url: str, content: str) -> None:
        raise PageCacheUnavailable


class DictCredentials:
    def __init__(self, key: str | None = "tvly") -> None:
        self.key = key

    def secret(self, user_id, kind: str, field: str) -> str | None:
        return self.key


def _service(provider: FakeProvider, store=None, key="tvly") -> WebSearchService:
    return WebSearchService(
        DictCredentials(key),
        store if store is not None else DictStore(),
        lambda api_key: provider,
    )


def test_reading_the_second_window_reuses_the_page_already_fetched():
    provider = FakeProvider(body="x" * 40)
    service = _service(provider)
    user = uuid4()

    first = service.fetch(user, "https://a", 0, 10)
    second = service.fetch(user, "https://a", 10, 10)

    assert first["content"] == "x" * 10
    assert first["truncated"] is True
    assert first["next_offset"] == 10
    assert second["content"] == "x" * 10
    assert provider.extract_calls == 1


def test_reading_past_the_end_reports_no_more_content():
    service = _service(FakeProvider(body="short"))
    result = service.fetch(uuid4(), "https://a", 99, 10)
    assert result["truncated"] is False
    assert result["next_offset"] is None
    assert result["content"] == ""


def test_another_user_never_reuses_a_cached_page():
    provider = FakeProvider(body="x" * 40)
    service = _service(provider, DictStore())

    service.fetch(uuid4(), "https://a", 0, 10)
    service.fetch(uuid4(), "https://a", 0, 10)

    assert provider.extract_calls == 2


def test_a_broken_cache_still_serves_the_page():
    provider = FakeProvider(body="x" * 40)
    service = _service(provider, FailingStore())

    result = service.fetch(uuid4(), "https://a", 0, 10)

    assert result["content"] == "x" * 10
    assert provider.extract_calls == 1


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ProviderRateLimited(), "rate_limited"),
        (ProviderQuotaExhausted(), "provider_quota_exhausted"),
        (WebPageNotFound(), "provider_unavailable"),
        (ProviderUnavailable(), "provider_unavailable"),
    ],
)
def test_provider_failures_surface_as_stable_codes(error, code):
    service = _service(FakeProvider(error=error))
    with pytest.raises(Exception) as caught:
        service.fetch(uuid4(), "https://a", 0, 10)
    assert str(caught.value.code) == code


def test_a_rejected_key_is_reported_as_a_configuration_problem():
    service = _service(FakeProvider(error=InvalidCredential()))
    with pytest.raises(InvalidWebCredentialError):
        service.search(uuid4(), "query", 5)


def test_reading_pages_without_a_key_says_it_is_not_configured():
    service = _service(FakeProvider(), key=None)
    with pytest.raises(Exception) as caught:
        service.fetch(uuid4(), "https://a", 0, 10)
    assert str(caught.value.code) == "provider_not_configured"


def test_page_cache_round_trips_and_expires_through_redis(shared_redis):
    cache = WebPageCache(shared_redis, ttl_seconds=60)
    user = uuid4().hex
    key = WebPageCache._key(user, "https://a")
    try:
        assert cache.get(user, "https://a") is None
        cache.put(user, "https://a", "body")
        assert cache.get(user, "https://a") == "body"
        assert 0 < shared_redis.ttl(key) <= 60
    finally:
        shared_redis.delete(key)
