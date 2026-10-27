"""Retry scheduling shared by every background worker.

A failed unit of work waits before it is tried again, and the wait grows each
time so a flaky dependency is not hammered. Each caller brings its own base and
ceiling: mail retries are cheap and frequent, a parsed paper is expensive.
"""

from datetime import UTC, datetime, timedelta

DEFAULT_BASE_SECONDS = 15
DEFAULT_MAX_SECONDS = 600


def backoff_seconds(
    attempts: int,
    *,
    base_seconds: float = DEFAULT_BASE_SECONDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> float:
    """How long to wait after the given number of failed attempts.

    ``attempts`` counts failures so far, so the first failure waits
    ``base_seconds`` and each later one doubles it, capped at ``max_seconds``.
    """
    exponent = max(0, attempts - 1)
    return min(max_seconds, base_seconds * 2**exponent)


def next_attempt_at(
    attempts: int,
    *,
    base_seconds: float = DEFAULT_BASE_SECONDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    now: datetime | None = None,
) -> datetime:
    """The moment described by :func:`backoff_seconds`, as a timestamp."""
    start = now or datetime.now(UTC)
    return start + timedelta(
        seconds=backoff_seconds(
            attempts, base_seconds=base_seconds, max_seconds=max_seconds
        )
    )
