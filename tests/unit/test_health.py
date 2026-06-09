"""Unit tests for :mod:`resilience_kit.health`."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from resilience_kit.circuit_breaker.base import HealthSnapshot
from resilience_kit.health import HealthStatus, health_snapshot
from resilience_kit.recovery import (
    register_for_recovery,
    reset_recovery_state,
    unregister_for_recovery,
)


class _StubBackend:
    """Backend that returns a pre-canned :class:`HealthSnapshot`."""

    def __init__(self, alias: str, snapshot: HealthSnapshot) -> None:
        self.alias = alias
        self._snapshot = snapshot

    async def try_recover(self) -> bool:
        """Always claim recovery — recovery path isn't under test here."""
        return self._snapshot.healthy

    async def health_check(self) -> HealthSnapshot:
        """Return the canned snapshot."""
        return self._snapshot


class _SlowBackend:
    """Backend whose ``health_check`` sleeps past the aggregator's timeout."""

    alias = "slow"

    async def try_recover(self) -> bool:
        """Pretend nothing has changed."""
        return False

    async def health_check(self) -> HealthSnapshot:
        """Hang past the configured probe timeout."""
        await asyncio.sleep(10)
        return HealthSnapshot(healthy=True, backend="slow")


class _RaisingBackend:
    """Backend whose ``health_check`` raises."""

    alias = "boom"

    async def try_recover(self) -> bool:
        """Pretend nothing has changed."""
        return False

    async def health_check(self) -> HealthSnapshot:
        """Raise to simulate an upstream blowup."""
        msg = "kaboom"
        raise RuntimeError(msg)


@pytest.fixture(autouse=True)
def _reset_recovery() -> Iterator[None]:
    """Clean recovery roster around every test."""
    reset_recovery_state()
    yield
    reset_recovery_state()


@pytest.mark.asyncio
async def test_empty_roster_is_ok() -> None:
    """No backends registered = memory-only deploy = OK."""
    agg = await health_snapshot()
    assert agg.status is HealthStatus.OK
    assert agg.http_status == 200


@pytest.mark.asyncio
async def test_all_healthy() -> None:
    """Every backend healthy → status=ok."""
    register_for_recovery(_StubBackend("a", HealthSnapshot(healthy=True, backend="a")))
    register_for_recovery(_StubBackend("b", HealthSnapshot(healthy=True, backend="b")))
    agg = await health_snapshot()
    assert agg.status is HealthStatus.OK


@pytest.mark.asyncio
async def test_some_unhealthy_is_degraded_but_serving() -> None:
    """Some backends degraded but at least one healthy → degraded-but-serving."""
    register_for_recovery(_StubBackend("a", HealthSnapshot(healthy=True, backend="a")))
    register_for_recovery(_StubBackend("b", HealthSnapshot(healthy=False, backend="b")))
    agg = await health_snapshot()
    assert agg.status is HealthStatus.DEGRADED_BUT_SERVING
    assert agg.http_status == 200


@pytest.mark.asyncio
async def test_all_unhealthy_is_degraded() -> None:
    """Every backend down → status=degraded → HTTP 503."""
    register_for_recovery(_StubBackend("a", HealthSnapshot(healthy=False, backend="a")))
    register_for_recovery(_StubBackend("b", HealthSnapshot(healthy=False, backend="b")))
    agg = await health_snapshot()
    assert agg.status is HealthStatus.DEGRADED
    assert agg.http_status == 503


@pytest.mark.asyncio
async def test_probe_timeout_counts_as_unhealthy() -> None:
    """A backend that exceeds the timeout is reported unhealthy with detail='timeout'."""
    slow = _SlowBackend()
    register_for_recovery(slow)
    agg = await health_snapshot(probe_timeout=0.05)
    assert agg.status is HealthStatus.DEGRADED
    assert agg.snapshots[0].healthy is False
    assert agg.snapshots[0].detail == "timeout"
    unregister_for_recovery(slow)


@pytest.mark.asyncio
async def test_probe_exception_is_captured() -> None:
    """A raising health_check is captured into a snapshot rather than propagated."""
    boom = _RaisingBackend()
    register_for_recovery(boom)
    agg = await health_snapshot()
    assert agg.status is HealthStatus.DEGRADED
    assert agg.snapshots[0].healthy is False
    assert "RuntimeError" in (agg.snapshots[0].detail or "")
