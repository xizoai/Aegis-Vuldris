"""Shared pytest fixtures for the Aegis Vuldris test suite."""

import pytest
from app.security.rate_limit import reset_rate_limiters


@pytest.fixture(autouse=True)
def _reset_rate_limiters() -> None:
    """Reset in-memory rate limiter state before every test.

    Rate limiters are module-level singletons so they behave correctly
    across requests in a running process. Without this reset, tests that
    call /auth/login or /auth/register more than a handful of times across
    a single pytest run would start tripping the same limits a real
    deployment would enforce, causing unrelated tests to fail.
    """

    reset_rate_limiters()
