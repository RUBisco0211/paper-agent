"""Backoff scheduling behaves the same for every caller that shares it."""

from datetime import UTC, datetime

import pytest

from app.platform.backoff import backoff_seconds, next_attempt_at


class TestBackoffSeconds:
    def test_first_failure_waits_the_base_delay(self) -> None:
        assert backoff_seconds(1, base_seconds=15) == 15

    def test_each_later_failure_doubles_the_wait(self) -> None:
        assert backoff_seconds(4, base_seconds=15) == 120

    def test_wait_never_exceeds_the_ceiling(self) -> None:
        assert backoff_seconds(20, base_seconds=15, max_seconds=600) == 600

    def test_mail_parameters_reproduce_the_previous_schedule(self) -> None:
        """The mail worker's old formula was min(600, 15 * 2 ** (n - 1))."""
        for attempts in (1, 2, 3, 4, 5, 6, 7, 8):
            expected = min(600, 15 * 2 ** (attempts - 1))
            assert (
                backoff_seconds(attempts, base_seconds=15, max_seconds=600)
                == expected
            )

    def test_stage_retries_use_their_own_base_and_ceiling(self) -> None:
        assert backoff_seconds(1, base_seconds=60, max_seconds=300) == 60
        assert backoff_seconds(2, base_seconds=60, max_seconds=300) == 120
        assert backoff_seconds(9, base_seconds=60, max_seconds=300) == 300

    @pytest.mark.parametrize("attempts", [0, -1])
    def test_a_non_positive_count_still_waits_the_base(self, attempts: int) -> None:
        # Defensive: callers increment before asking, but a fresh row reads 0.
        assert backoff_seconds(attempts, base_seconds=15) == 15


class TestNextAttemptAt:
    def test_returns_a_moment_offset_from_now(self) -> None:
        now = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
        assert next_attempt_at(
            2, base_seconds=60, max_seconds=300, now=now
        ) == datetime(2026, 10, 27, 12, 2, tzinfo=UTC)

    def test_defaults_to_the_current_moment(self) -> None:
        before = datetime.now(UTC)
        scheduled = next_attempt_at(1, base_seconds=60)
        assert scheduled > before
