"""Behaviour contract for every :class:`AsyncThrottle` backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from resilience_kit.throttle import Rate

if TYPE_CHECKING:
    from collections.abc import Callable

    from resilience_kit.testing import FakeClock
    from resilience_kit.throttle.base import AsyncThrottle


async def test_admits_up_to_limit(
    throttle_factory: Callable[..., AsyncThrottle],
    clock: FakeClock,
) -> None:
    throttle = throttle_factory(clock=clock)
    rate = Rate(count=3, per_seconds=60)
    decisions = [await throttle.check("k", rate) for _ in range(3)]
    assert all(d.allowed for d in decisions)
    assert decisions[-1].remaining == 0


async def test_denies_above_limit(
    throttle_factory: Callable[..., AsyncThrottle],
    clock: FakeClock,
) -> None:
    throttle = throttle_factory(clock=clock)
    rate = Rate(count=2, per_seconds=60)
    await throttle.check("k", rate)
    await throttle.check("k", rate)
    decision = await throttle.check("k", rate)
    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.reset_after > 0


async def test_window_slides(
    throttle_factory: Callable[..., AsyncThrottle],
    clock: FakeClock,
) -> None:
    throttle = throttle_factory(clock=clock)
    rate = Rate(count=2, per_seconds=60)
    await throttle.check("k", rate)
    await throttle.check("k", rate)
    assert (await throttle.check("k", rate)).allowed is False
    # Advance past the window; old entries drop and we should be admitted again.
    clock.tick(61)
    assert (await throttle.check("k", rate)).allowed is True


async def test_keys_are_isolated(
    throttle_factory: Callable[..., AsyncThrottle],
    clock: FakeClock,
) -> None:
    throttle = throttle_factory(clock=clock)
    rate = Rate(count=1, per_seconds=60)
    assert (await throttle.check("alice", rate)).allowed is True
    assert (await throttle.check("bob", rate)).allowed is True
    # Each has used their one slot.
    assert (await throttle.check("alice", rate)).allowed is False
    assert (await throttle.check("bob", rate)).allowed is False


async def test_reset_clears_key(
    throttle_factory: Callable[..., AsyncThrottle],
    clock: FakeClock,
) -> None:
    throttle = throttle_factory(clock=clock)
    rate = Rate(count=1, per_seconds=60)
    await throttle.check("k", rate)
    assert (await throttle.check("k", rate)).allowed is False
    await throttle.reset("k")
    assert (await throttle.check("k", rate)).allowed is True


async def test_health_check(
    throttle_factory: Callable[..., AsyncThrottle],
    clock: FakeClock,
) -> None:
    throttle = throttle_factory(clock=clock)
    snap = await throttle.health_check()
    assert snap.healthy is True
    assert snap.backend == throttle_factory.backend  # type: ignore[attr-defined]


async def test_rate_parse_roundtrips() -> None:
    assert Rate.parse("60/min") == Rate(count=60, per_seconds=60.0)
    assert Rate.parse("10/sec") == Rate(count=10, per_seconds=1.0)
    assert Rate.parse("1000/hour") == Rate(count=1000, per_seconds=3600.0)
    assert Rate.parse("2/day") == Rate(count=2, per_seconds=86400.0)
