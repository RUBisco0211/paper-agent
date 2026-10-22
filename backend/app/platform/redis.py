"""Process-wide Redis client shared by every feature that needs short-lived state.

A single client owns one connection pool; opening a connection per request
would cost a TCP handshake on paths the agent can call repeatedly.
"""

from redis import Redis

from .config import settings

_client: Redis | None = None


def get_redis() -> Redis:
    """Return the shared client, creating the pool on first use."""
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _client


def set_redis(client: Redis | None) -> None:
    """Replace or clear the shared client; used by tests and shutdown."""
    global _client
    _client = client
