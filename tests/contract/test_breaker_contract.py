"""Behaviour contract for every :class:`AsyncBreaker` backend."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from resilience_kit.circuit_breaker.base import BreakerConfig, BreakerState
from resilience_kit.exceptions import (
    ExternalServiceError,
    ServiceUnavailableError,
    TransientError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from resilience_kit.circuit_breaker.base import AsyncBreaker
    from resilience_kit.testing import FakeClock


async def _ok() -> str:
    return "ok"


async def _boom() -> None:
    raise TransientError("boom")


async def test_closed_passes_calls(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    breaker = breaker_factory("svc", BreakerConfig(fail_max=3), clock=clock)
    for _ in range(5):
        assert await breaker.call(_ok) == "ok"
    assert await breaker.state() is BreakerState.CLOSED


async def test_opens_after_fail_max(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    breaker = breaker_factory("svc", BreakerConfig(fail_max=2, reset_timeout=10), clock=clock)
    for _ in range(2):
        with pytest.raises(TransientError):
            await breaker.call(_boom)
    assert await breaker.state() is BreakerState.OPEN
    # OPEN short-circuits subsequent calls.
    with pytest.raises(ServiceUnavailableError):
        await breaker.call(_ok)


async def test_half_open_then_closed_on_successes(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    if breaker_factory.backend == "pybreaker":  # type: ignore[attr-defined]
        pytest.skip("pybreaker has no injectable clock; covered by real-time tests")
    breaker = breaker_factory(
        "svc",
        BreakerConfig(fail_max=2, reset_timeout=5, success_threshold=2),
        clock=clock,
    )
    for _ in range(2):
        with pytest.raises(TransientError):
            await breaker.call(_boom)
    assert await breaker.state() is BreakerState.OPEN

    clock.tick(6)
    assert await breaker.state() is BreakerState.HALF_OPEN

    # success_threshold=2 → two successes to close.
    assert await breaker.call(_ok) == "ok"
    assert await breaker.state() is BreakerState.HALF_OPEN
    assert await breaker.call(_ok) == "ok"
    assert await breaker.state() is BreakerState.CLOSED


async def test_half_open_failure_reopens_immediately(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    if breaker_factory.backend == "pybreaker":  # type: ignore[attr-defined]
        pytest.skip("pybreaker has no injectable clock; covered by real-time tests")
    breaker = breaker_factory(
        "svc",
        BreakerConfig(fail_max=2, reset_timeout=5),
        clock=clock,
    )
    for _ in range(2):
        with pytest.raises(TransientError):
            await breaker.call(_boom)
    clock.tick(6)
    assert await breaker.state() is BreakerState.HALF_OPEN
    with pytest.raises(TransientError):
        await breaker.call(_boom)
    assert await breaker.state() is BreakerState.OPEN


async def test_excluded_exceptions_do_not_count(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    breaker = breaker_factory(
        "svc",
        BreakerConfig(fail_max=2, excluded_exceptions=(ValueError,)),
        clock=clock,
    )

    async def raises_value() -> None:
        raise ValueError("excluded")

    for _ in range(5):
        with pytest.raises(ValueError):
            await breaker.call(raises_value)
    assert await breaker.state() is BreakerState.CLOSED


async def test_default_excluded_exceptions_do_not_count(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    """The default config excludes caller/programmer errors (#B3).

    With no explicit ``excluded_exceptions``, a ``ValueError`` raised by
    business logic must NOT trip a transport-failure breaker.
    """
    breaker = breaker_factory("svc", BreakerConfig(fail_max=2), clock=clock)

    async def raises_value() -> None:
        raise ValueError("bad input — not the service's fault")

    for _ in range(5):
        with pytest.raises(ValueError):
            await breaker.call(raises_value)
    assert await breaker.state() is BreakerState.CLOSED


async def test_cancellation_does_not_count(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    breaker = breaker_factory("svc", BreakerConfig(fail_max=2), clock=clock)

    async def cancels() -> None:
        raise asyncio.CancelledError

    for _ in range(5):
        with pytest.raises(asyncio.CancelledError):
            await breaker.call(cancels)
    assert await breaker.state() is BreakerState.CLOSED


async def test_reset_returns_to_closed(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    breaker = breaker_factory("svc", BreakerConfig(fail_max=1), clock=clock)
    with pytest.raises(TransientError):
        await breaker.call(_boom)
    assert await breaker.state() is BreakerState.OPEN
    await breaker.reset()
    assert await breaker.state() is BreakerState.CLOSED


async def test_health_check_returns_snapshot(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    breaker = breaker_factory("svc", BreakerConfig(), clock=clock)
    snap = await breaker.health_check()
    assert snap.healthy is True
    assert snap.backend == breaker_factory.backend  # type: ignore[attr-defined]


async def test_failure_then_success_resets_counter(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    breaker = breaker_factory("svc", BreakerConfig(fail_max=3), clock=clock)
    with pytest.raises(TransientError):
        await breaker.call(_boom)
    with pytest.raises(TransientError):
        await breaker.call(_boom)
    # A success in CLOSED state resets the failure counter.
    assert await breaker.call(_ok) == "ok"
    with pytest.raises(TransientError):
        await breaker.call(_boom)
    with pytest.raises(TransientError):
        await breaker.call(_boom)
    # Only 2 consecutive failures since the success → still CLOSED.
    assert await breaker.state() is BreakerState.CLOSED


async def test_concurrent_callers_see_consistent_state(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    breaker = breaker_factory(
        "svc",
        BreakerConfig(fail_max=5, reset_timeout=10),
        clock=clock,
    )

    async def attempt() -> None:
        with pytest.raises((TransientError, ServiceUnavailableError)):
            await breaker.call(_boom)

    await asyncio.gather(*[attempt() for _ in range(20)])
    # 20 racing failures → eventually OPEN.
    assert await breaker.state() is BreakerState.OPEN


async def test_non_retryable_exception_still_counts_as_failure(
    breaker_factory: Callable[..., AsyncBreaker],
    clock: FakeClock,
) -> None:
    """A non-transient exception still trips the breaker.

    ExternalServiceError is the canonical "upstream returned non-success" signal —
    not retryable but very much a breaker-failure.
    """
    breaker = breaker_factory("svc", BreakerConfig(fail_max=2), clock=clock)

    async def upstream_400() -> None:
        raise ExternalServiceError("upstream said no")

    for _ in range(2):
        with pytest.raises(ExternalServiceError):
            await breaker.call(upstream_400)
    assert await breaker.state() is BreakerState.OPEN
