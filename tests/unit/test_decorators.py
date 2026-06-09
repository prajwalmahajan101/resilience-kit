"""``@circuit_breaker`` and ``@resilient`` decorator behaviour."""

from __future__ import annotations

import asyncio

import pytest

from resilience_kit import circuit_breaker, registry, resilient
from resilience_kit.exceptions import ServiceUnavailableError, TransientError


async def test_circuit_breaker_async_short_circuits_when_open() -> None:
    registry.register_service("svc", {"circuit_breaker": {"fail_max": 1}})

    @circuit_breaker("svc")
    async def boom() -> None:
        raise TransientError("boom")

    with pytest.raises(TransientError):
        await boom()
    with pytest.raises(ServiceUnavailableError):
        await boom()


async def test_resilient_retries_then_opens() -> None:
    registry.register_service(
        "svc",
        {
            "retry": {"max_attempts": 2, "wait_min": 0.001, "wait_max": 0.001},
            "circuit_breaker": {"fail_max": 2},
        },
    )
    calls = 0

    @resilient("svc")
    async def upstream() -> None:
        nonlocal calls
        calls += 1
        raise TransientError("boom")

    with pytest.raises(TransientError):
        await upstream()
    with pytest.raises(TransientError):
        await upstream()
    with pytest.raises(ServiceUnavailableError):
        await upstream()
    # 2 batches of 2 attempts = 4. The OPEN call short-circuits.
    assert calls == 4


def test_sync_circuit_breaker_refuses_inside_running_loop() -> None:
    @circuit_breaker("svc")
    def sync_func() -> None: ...

    async def run_from_loop() -> None:
        sync_func()

    with pytest.raises(RuntimeError, match="running event loop"):
        asyncio.run(run_from_loop())
