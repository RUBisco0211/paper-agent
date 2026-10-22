"""What the web capability needs from its environment, and the Tavily adapter.

The service receives a provider, a credential reader and a page store, so this
package never opens a connection of its own. The provider's wire format stays in
one place so a different service only replaces this file.
"""

from collections.abc import Callable
from typing import Protocol

import httpx

from ..platform.outbound_http import HttpClientFactory, default_http_client_factory
from .domain import (
    InvalidCredential,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderUnavailable,
    WebPageNotFound,
)


class WebProvider(Protocol):
    """One provider's search and page reads."""

    def search(self, query: str, max_results: int) -> list[dict]: ...

    def extract(self, url: str) -> str: ...

    def extract_excerpt(self, url: str, query: str, chunks: int) -> str: ...


class PageStore(Protocol):
    """Cache of whole page bodies, keyed by owner and URL."""

    def get(self, user_id: str, url: str) -> str | None: ...

    def put(self, user_id: str, url: str, content: str) -> None: ...


class CredentialReader(Protocol):
    """Reads one user's secret for one service."""

    def secret(self, user_id, kind: str, field: str) -> str | None: ...


ProviderFactory = Callable[[str], WebProvider]


def _raising_for_status(status_code: int) -> None:
    if status_code == 401:
        raise InvalidCredential
    if status_code == 429:
        raise ProviderRateLimited
    if status_code in {432, 433}:
        raise ProviderQuotaExhausted
    if status_code >= 400:
        raise ProviderUnavailable


class TavilyWeb:
    """Tavily search and extraction; the page body is returned unmodified."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        http_factory: HttpClientFactory | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._http_factory = http_factory or default_http_client_factory

    def _post(self, path: str, payload: dict) -> dict:
        try:
            with self._http_factory() as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                    timeout=self._timeout,
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable from exc
        _raising_for_status(response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderUnavailable from exc

    def search(self, query: str, max_results: int) -> list[dict]:
        data = self._post(
            "/search",
            {
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "topic": "general",
                "include_raw_content": False,
            },
        )
        results = data.get("results")
        if not isinstance(results, list):
            return []
        return [
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": item.get("content") or "",
            }
            for item in results
            if isinstance(item, dict) and item.get("url")
        ]

    def extract(self, url: str) -> str:
        return self._body(
            {
                "urls": [url],
                "format": "markdown",
                "extract_depth": "basic",
            }
        )

    def extract_excerpt(self, url: str, query: str, chunks: int) -> str:
        return self._body(
            {
                "urls": [url],
                "format": "markdown",
                "extract_depth": "basic",
                "query": query,
                "chunks_per_source": max(1, min(chunks, 5)),
            }
        )

    def _body(self, payload: dict) -> str:
        data = self._post("/extract", payload)
        for item in data.get("results") or []:
            if isinstance(item, dict) and item.get("raw_content"):
                return item["raw_content"]
        raise WebPageNotFound
