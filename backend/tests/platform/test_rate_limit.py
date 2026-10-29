"""The token bucket paces callers and is shared across processes."""

import pytest

from app.platform.rate_limit import TokenBucket, estimate_tokens


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def bucket_factory(auth_redis):
    def _make(name: str, *, rpm: float = 0, tpm: float = 0, clock=None):
        clock = clock or FakeClock()
        bucket = TokenBucket(
            client=auth_redis,
            name=name,
            requests_per_minute=rpm,
            tokens_per_minute=tpm,
            clock=clock.clock,
            sleep=clock.sleep,
        )
        return bucket, clock

    return _make


class TestRequestRate:
    def test_calls_beyond_the_burst_wait(self, bucket_factory) -> None:
        bucket, clock = bucket_factory("req", rpm=60)
        for _ in range(60):
            bucket.acquire()
        assert clock.slept == []

        bucket.acquire()
        assert sum(clock.slept) > 0


class TestTokenRate:
    def test_a_heavy_call_waits_for_enough_tokens(self, bucket_factory) -> None:
        bucket, clock = bucket_factory("tok", tpm=60)
        bucket.acquire(tokens=30)
        bucket.acquire(tokens=30)
        assert clock.slept == []

        bucket.acquire(tokens=30)
        assert sum(clock.slept) > 0


class TestSharedAcrossProcesses:
    def test_two_buckets_with_the_same_name_share_one_allowance(
        self, bucket_factory
    ) -> None:
        """Two workers must not each spend the whole minute's quota."""
        first, first_clock = bucket_factory("shared", rpm=60)
        second, second_clock = bucket_factory("shared", rpm=60)

        for _ in range(60):
            first.acquire()
        assert first_clock.slept == []

        # The second worker sees the allowance already spent.
        second.acquire()
        assert sum(second_clock.slept) > 0

    def test_different_names_do_not_interfere(self, bucket_factory) -> None:
        bucket_a, _clock_a = bucket_factory("a", rpm=60)
        bucket_b, clock_b = bucket_factory("b", rpm=60)
        for _ in range(60):
            bucket_a.acquire()

        bucket_b.acquire()
        assert clock_b.slept == []


class TestUnlimited:
    def test_no_limits_means_no_redis_traffic(self) -> None:
        # A self-hosted service has no quota; nothing should be asked of Redis.
        bucket = TokenBucket(
            client=None, name="local", requests_per_minute=0, tokens_per_minute=0
        )
        bucket.acquire(tokens=10_000)


class TestEstimating:
    def test_latin_text_uses_four_characters_per_token(self) -> None:
        assert estimate_tokens("a" * 400) == 100

    def test_chinese_text_is_counted_conservatively(self) -> None:
        """CJK packs more meaning per character, so it must not be undercounted."""
        assert estimate_tokens("中" * 300) == 300

    def test_mixed_text_counts_each_script_separately(self) -> None:
        assert estimate_tokens("中" * 150 + "a" * 200) == 200

    def test_never_returns_zero_tokens(self) -> None:
        assert estimate_tokens("") == 1


class TestOversizedRequest:
    def test_a_call_larger_than_the_bucket_is_refused(self, bucket_factory) -> None:
        """Waiting for more than the bucket can hold would never finish."""
        bucket, clock = bucket_factory("oversized", tpm=1000)

        with pytest.raises(ValueError):
            bucket.acquire(tokens=2000)

        # It must fail fast rather than block the calling thread.
        assert clock.slept == []


class TestSingleOversizedInput:
    def test_a_single_passage_too_large_is_a_stable_error(self) -> None:
        """The adapter must not leak a bare ValueError into the stage failure."""
        from app.literature_support.embedding.client import (
            OpenAICompatibleEmbeddingAdapter,
        )
        from app.platform.errors import AppError, ErrorCode
        from app.platform.rate_limit import TokenBucket

        bucket = TokenBucket(client=None, name="tiny", tokens_per_minute=10)
        client = OpenAICompatibleEmbeddingAdapter(
            base_url="https://example.test/v1",
            api_key="k",
            bucket=bucket,
        )
        with pytest.raises(AppError) as caught:
            client._embed(["中" * 2000])
        assert caught.value.code is ErrorCode.EMBEDDING_INPUT_TOO_LARGE
