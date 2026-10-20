"""Tests for the in-memory sliding-window rate limiter."""

import time

import pytest
from app.api.errors import RateLimitExceededError
from app.security.rate_limit import SlidingWindowRateLimiter


def test_allows_requests_within_limit() -> None:
    """Requests at or under the limit within the window succeed."""

    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)

    for _ in range(3):
        limiter.check("client-a")


def test_blocks_requests_over_limit() -> None:
    """A request beyond the limit within the window raises RateLimitExceededError."""

    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)

    for _ in range(3):
        limiter.check("client-a")

    with pytest.raises(RateLimitExceededError):
        limiter.check("client-a")


def test_limit_is_tracked_independently_per_key() -> None:
    """Different keys (clients) have independent rate limit budgets."""

    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)

    limiter.check("client-a")

    with pytest.raises(RateLimitExceededError):
        limiter.check("client-a")

    # A different client key is unaffected by client-a's usage.
    limiter.check("client-b")


def test_reset_clears_tracked_hits() -> None:
    """Calling reset() clears all tracked usage, as used for test isolation."""

    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)

    limiter.check("client-a")
    limiter.reset()

    # Would have raised RateLimitExceededError if the reset had not cleared state.
    limiter.check("client-a")


def test_exceeded_error_reports_a_positive_retry_after() -> None:
    """RateLimitExceededError always reports a retry_after_seconds of at least 1."""

    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)

    limiter.check("client-a")

    with pytest.raises(RateLimitExceededError) as exc_info:
        limiter.check("client-a")

    assert exc_info.value.retry_after_seconds >= 1


def test_stale_keys_are_pruned_once_the_table_grows() -> None:
    """An attacker cycling keys cannot grow the hit table without bound.

    Once the table exceeds MAX_TRACKED_KEYS, keys whose newest hit has already
    aged out of the window are dropped on the next check.
    """

    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    limiter.MAX_TRACKED_KEYS = 1

    expired = time.monotonic() - 120
    limiter._hits["old-a"] = [expired]
    limiter._hits["old-b"] = [expired]

    limiter.check("fresh")

    assert "old-a" not in limiter._hits
    assert "old-b" not in limiter._hits
    assert "fresh" in limiter._hits


def test_pruning_keeps_keys_with_recent_hits() -> None:
    """A key with a hit still inside the window survives pruning."""

    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
    limiter.MAX_TRACKED_KEYS = 1

    limiter.check("active")
    limiter._hits["stale"] = [time.monotonic() - 120]

    # len(_hits) is now 2, above the threshold, so this check prunes.
    limiter.check("other")

    assert "active" in limiter._hits
    assert "stale" not in limiter._hits
