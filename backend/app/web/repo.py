"""Redis-backed page cache so one fetched page can be read across calls.

Only whole-page reads are cached. The excerpt mode skips it on purpose: its
result is scoped to the query that produced it and would not be reusable.
"""

import hashlib
import json

from redis import Redis
from redis.exceptions import RedisError

TTL_SECONDS = 3600


class PageCacheUnavailable(Exception):
    """Raised when Redis cannot serve the cache; callers fall back to the network."""


class WebPageCache:
    def __init__(self, redis: Redis, *, ttl_seconds: int = TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(user_id: str, url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return f"web_page:{user_id}:{digest}"

    def get(self, user_id: str, url: str) -> str | None:
        try:
            raw = self._redis.get(self._key(user_id, url))
        except RedisError as exc:
            raise PageCacheUnavailable from exc
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise PageCacheUnavailable from exc
        content = payload.get("content")
        return content if isinstance(content, str) else None

    def put(self, user_id: str, url: str, content: str) -> None:
        try:
            self._redis.set(
                self._key(user_id, url),
                json.dumps({"url": url, "content": content}),
                ex=self._ttl,
            )
        except RedisError as exc:
            raise PageCacheUnavailable from exc
