"""Behaviour contract for ``@retry``.

Retry has only one implementation (it's pure logic, no backend) — the
contract suite still parametrizes for symmetry with the other primitives
and to catch sync/async regressions.
"""

from __future__ import annotations

import asyncio

import pytest

from resilience_kit.exceptions import ServiceUnavailableError, TransientError
from resilience_kit.retry import retry


async def test_async_retries_then_succeeds() -> None:
    attempts = 0

    @retry(max_attempts=3, base_delay=0.001, max_delay=0.001, exceptions=(TransientError,))
    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientError("once more")
        return "ok"

    assert await flaky() == "ok"
    assert attempts == 3


async def test_async_exhaust_raises() -> None:
    attempts = 0

    @retry(max_attempts=2, base_delay=0.001, max_delay=0.001, exceptions=(TransientError,))
    async def always_fails() -> None:
        nonlocal attempts
        attempts += 1
        raise TransientError("boom")

    with pytest.raises(TransientError):
        await always_fails()
    assert attempts == 2


async def test_non_listed_exception_propagates_immediately() -> None:
    attempts = 0

    @retry(max_attempts=5, base_delay=0.001, exceptions=(TransientError,))
    async def value_err() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        await value_err()
    assert attempts == 1


async def test_service_unavailable_filtered_out() -> None:
    """``ServiceUnavailableError`` must NEVER be retried even if listed."""
    attempts = 0

    @retry(max_attempts=5, base_delay=0.001, exceptions=(ServiceUnavailableError, Exception))
    async def breaker_open() -> None:
        nonlocal attempts
        attempts += 1
        raise ServiceUnavailableError("svc")

    with pytest.raises(ServiceUnavailableError):
        await breaker_open()
    # No retries — even though ServiceUnavailableError was in the list.
    assert attempts == 1


async def test_on_error_callback_fires_per_attempt() -> None:
    seen: list[tuple[int, str]] = []

    def on_error(exc: BaseException, attempt: int) -> None:
        seen.append((attempt, str(exc)))

    @retry(
        max_attempts=3,
        base_delay=0.001,
        max_delay=0.001,
        exceptions=(TransientError,),
        on_error=on_error,
    )
    async def always_fails() -> None:
        raise TransientError("boom")

    with pytest.raises(TransientError):
        await always_fails()
    assert [a for a, _ in seen] == [1, 2, 3]


def test_sync_retries() -> None:
    attempts = 0

    @retry(max_attempts=3, base_delay=0.001, max_delay=0.001, exceptions=(TransientError,))
    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientError("once more")
        return "ok"

    assert flaky() == "ok"
    assert attempts == 3


def test_sync_exhaust_raises() -> None:
    @retry(max_attempts=2, base_delay=0.001, max_delay=0.001, exceptions=(TransientError,))
    def always_fails() -> None:
        raise TransientError("boom")

    with pytest.raises(TransientError):
        always_fails()


async def test_raise_on_failure_false_returns_none() -> None:
    @retry(
        max_attempts=2,
        base_delay=0.001,
        max_delay=0.001,
        exceptions=(TransientError,),
        raise_on_failure=False,
    )
    async def always_fails() -> str:
        raise TransientError("boom")

    assert await always_fails() is None


async def test_cancellation_propagates_unchanged() -> None:
    @retry(max_attempts=5, base_delay=0.001, exceptions=(Exception,))
    async def cancels() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await cancels()
