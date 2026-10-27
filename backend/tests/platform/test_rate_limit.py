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
    def test_estimates_tokens_pessimistically(self) -> None:
        assert estimate_tokens(3000) == 1000

    def test_never_returns_zero_tokens(self) -> None:
        assert estimate_tokens(0) == 1
