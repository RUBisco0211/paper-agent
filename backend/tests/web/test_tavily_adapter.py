"""The provider adapter maps Tavily's wire format onto stable failures."""

import json

import httpx
import pytest

from app.web.domain import (
    InvalidCredential,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderUnavailable,
    WebPageNotFound,
)
from app.web.ports import TavilyWeb


def _web(handler) -> TavilyWeb:
    transport = httpx.MockTransport(handler)
    return TavilyWeb(
        api_key="tvly-test",
        base_url="https://api.tavily.test",
        timeout_seconds=5.0,
        http_factory=lambda: httpx.Client(transport=transport),
    )


def _error(status: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": {"error": "nope"}})

    return handler


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, InvalidCredential),
        (429, ProviderRateLimited),
        (432, ProviderQuotaExhausted),
        (433, ProviderQuotaExhausted),
        (500, ProviderUnavailable),
        (503, ProviderUnavailable),
    ],
)
def test_tavily_http_errors_map_to_provider_failures(status, expected):
    with pytest.raises(expected):
        _web(_error(status)).search("query", 5)


def test_a_transport_failure_reads_as_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(ProviderUnavailable):
        _web(handler).search("query", 5)


def test_search_normalises_hits_and_drops_entries_without_a_url():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Hit", "url": "https://a", "content": "snippet"},
                    {"title": "Broken"},
                ]
            },
        )

    results = _web(handler).search("query", 5)

    assert results == [{"title": "Hit", "url": "https://a", "snippet": "snippet"}]


def test_an_empty_result_set_is_not_a_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    assert _web(handler).search("query", 5) == []


def test_a_payload_without_results_is_a_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(ProviderUnavailable):
        _web(handler).search("query", 5)


def test_extract_returns_the_body_untouched():
    body = "# Title\n\nSome *markdown*."

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"results": [{"url": "https://a", "raw_content": body}]}
        )

    assert _web(handler).extract("https://a") == body


def test_extract_reports_a_failed_url_as_a_missing_page():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [],
                "failed_results": [{"url": "https://a", "error": "boom"}],
            },
        )

    with pytest.raises(WebPageNotFound):
        _web(handler).extract("https://a")


def test_excerpt_requests_passages_chosen_by_the_query():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, json={"results": [{"url": "https://a", "raw_content": "passage"}]}
        )

    assert _web(handler).extract_excerpt("https://a", "what is RSC", 4) == "passage"
    assert seen["query"] == "what is RSC"
    assert seen["chunks_per_source"] == 4
