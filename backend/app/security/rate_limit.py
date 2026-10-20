"""In-memory sliding-window rate limiting for sensitive Aegis Vuldris endpoints.

This is intentionally dependency-free (stdlib only) so it works without
adding a new package to pyproject.toml. It limits requests per client IP
within a rolling time window, held in process memory.

Caveat: because state is in-process, this only enforces limits correctly
for a single running instance. If Aegis Vuldris is deployed with multiple
worker processes or replicas (see Phase 6 - deployment/CI), replace this
with a shared-state limiter (e.g. Redis-backed) so limits are enforced
consistently across all instances.
"""

import time
from collections import defaultdict
from threading import Lock

from fastapi import Request

from app.api.errors import RateLimitExceededError


class SlidingWindowRateLimiter:
    """Tracks request timestamps per key within a rolling time window."""

    # Distinct client keys held in memory. An attacker cycling source addresses
    # would otherwise grow ``_hits`` without bound, so once the table exceeds
    # this size keys whose newest hit has aged out of the window are dropped.
    MAX_TRACKED_KEYS: int = 10_000

    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _prune_stale(self, window_start: float) -> None:
        """Drop keys whose every recorded hit predates the current window.

        Called only once the table has grown past ``MAX_TRACKED_KEYS`` so the
        common case pays nothing; the caller holds ``_lock``.
        """

        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < window_start]
        for key in stale:
            del self._hits[key]

    def check(self, key: str) -> None:
        """Record a hit for ``key`` and raise RateLimitExceededError if over limit."""

        now = time.monotonic()
        window_start = now - self.window_seconds

        with self._lock:
            if len(self._hits) > self.MAX_TRACKED_KEYS:
                self._prune_stale(window_start)
            timestamps = self._hits[key]
            # Drop timestamps outside the current window.
            while timestamps and timestamps[0] < window_start:
                timestamps.pop(0)

            if len(timestamps) >= self.max_requests:
                retry_after = int(self.window_seconds - (now - timestamps[0])) + 1
                raise RateLimitExceededError(retry_after_seconds=max(retry_after, 1))

            timestamps.append(now)

    def reset(self) -> None:
        """Clear all tracked hits. Intended for test isolation only."""

        with self._lock:
            self._hits.clear()


# Separate limiters per endpoint so a burst on one doesn't consume the
# other's budget. Limits are deliberately conservative for auth endpoints,
# which are the most common brute-force / credential-stuffing targets.
login_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)
register_rate_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)


def _client_key(request: Request) -> str:
    """Return a best-effort client identifier for rate limiting.

    Uses the immediate connecting client's IP. If Aegis Vuldris is deployed
    behind a trusted reverse proxy, this should be updated to read the
    proxy's forwarded-for header instead - only once that proxy is known
    to be the sole entry point, since trusting client-supplied headers
    directly would let the limiter be bypassed by spoofing them.
    """

    if request.client is None:
        return "unknown"
    return request.client.host


def enforce_login_rate_limit(request: Request) -> None:
    """FastAPI dependency: enforce the login endpoint's rate limit."""

    login_rate_limiter.check(_client_key(request))


def enforce_register_rate_limit(request: Request) -> None:
    """FastAPI dependency: enforce the registration endpoint's rate limit."""

    register_rate_limiter.check(_client_key(request))


def reset_rate_limiters() -> None:
    """Reset all module-level rate limiters. Intended for test isolation only."""

    login_rate_limiter.reset()
    register_rate_limiter.reset()


__all__ = [
    "RateLimitExceededError",
    "SlidingWindowRateLimiter",
    "enforce_login_rate_limit",
    "enforce_register_rate_limit",
    "reset_rate_limiters",
]
