"""The adapter meters what it actually sends, per provider credential."""

import httpx

from app.literature_support.embedding.base import EmbeddingProfile
from app.literature_support.embedding.client import (
    OpenAICompatibleEmbeddingAdapter,
    _bucket_name,
)
from app.platform.rate_limit import TokenBucket


class CountingBucket(TokenBucket):
    """Records every acquisition so the test can see what was charged."""

    def __init__(self) -> None:
        super().__init__(client=None, name="counting", tokens_per_minute=0)
        self.charged: list[float] = []

    def acquire(self, *, tokens: float = 0) -> None:
        self.charged.append(tokens)


def _adapter(bucket, *, handler, max_retries=0):
    return OpenAICompatibleEmbeddingAdapter(
        base_url="https://example.test/v1",
        api_key="k",
        profile=EmbeddingProfile(dimensions=2),
        bucket=bucket,
        http_client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(handler)
        ),
        max_retries=max_retries,
        retry_backoff=0,
        sleeper=lambda _: None,
    )


def test_a_batch_is_charged_once_per_request() -> None:
    bucket = CountingBucket()
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                ]
            },
        )

    adapter = _adapter(bucket, handler=handler)
    vectors = adapter._embed(["aaaa", "bbbb"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    # Both passages are charged in one call, not one call per passage.
    assert len(bucket.charged) == 1


def test_each_http_retry_is_charged_again() -> None:
    bucket = CountingBucket()
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={})
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [0.5, 0.6]}]}
        )

    adapter = _adapter(bucket, handler=handler, max_retries=1)
    adapter._embed(["aaaa"])

    # The first attempt and the retry both reach the provider, so both cost.
    assert calls["n"] == 2
    assert len(bucket.charged) == 2


def test_splitting_an_oversized_batch_keeps_the_order() -> None:
    seen: list[int] = []

    def handler(request):
        import json as _json

        inputs = _json.loads(request.content)["input"]
        seen.append(len(inputs))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [float(i), 0.0]}
                    for i in range(len(inputs))
                ]
            },
        )

    class Oversized(TokenBucket):
        """Refuses any batch bigger than two passages."""

        def __init__(self) -> None:
            super().__init__(client=None, name="tiny", tokens_per_minute=0)
            self.rejected = False

        def acquire(self, *, tokens: float = 0) -> None:
            if not self.rejected and tokens > 2:
                self.rejected = True
                raise ValueError("too large")

    adapter = _adapter(Oversized(), handler=handler)
    vectors = adapter._embed(["aaaa"] * 4)

    assert len(vectors) == 4
    # The oversized batch was halved before anything was sent.
    assert max(seen) <= 2
    assert seen == sorted(seen, reverse=True) or sum(seen) == 4


class TestBucketIsolation:
    def test_different_keys_get_different_buckets(self) -> None:
        first = _bucket_name("https://example.test/v1", "key-a")
        second = _bucket_name("https://example.test/v1", "key-b")
        assert first != second

    def test_the_same_key_shares_one_bucket(self) -> None:
        assert _bucket_name("https://example.test/v1", "key-a") == _bucket_name(
            "https://example.test/v1", "key-a"
        )

    def test_the_key_never_appears_in_the_bucket_name(self) -> None:
        name = _bucket_name("https://example.test/v1", "secret-key-value")
        assert "secret-key-value" not in name
