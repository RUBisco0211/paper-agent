"""Shared outbound HTTP client construction for provider adapters."""

from collections.abc import Callable

import httpx

from .config import settings

HttpClientFactory = Callable[[], httpx.Client]


def default_http_client_factory() -> httpx.Client:
    return httpx.Client(
        timeout=settings.outbound_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "paper-agent/0.1 (metadata resolution)"},
    )
