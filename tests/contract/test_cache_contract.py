"""Behaviour contract for every :class:`AsyncCache` backend."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from resilience_kit.cache.base import AsyncCache
    from resilience_kit.testing import FakeClock


async def test_set_get_roundtrip(
    cache_factory: Callable[..., AsyncCache], clock: FakeClock
) -> None:
    cache = cache_factory(clock=clock)
    await cache.set("k", "v")
    assert await cache.get("k") == "v"


async def test_missing_returns_none(
    cache_factory: Callable[..., AsyncCache],
    clock: FakeClock,
) -> None:
    cache = cache_factory(clock=clock)
    assert await cache.get("absent") is None


async def test_ttl_expires(cache_factory: Callable[..., AsyncCache], clock: FakeClock) -> None:
    cache = cache_factory(clock=clock)
    await cache.set("k", "v", ttl=10)
    assert await cache.get("k") == "v"
    clock.tick(11)
    assert await cache.get("k") is None


async def test_add_nx(cache_factory: Callable[..., AsyncCache], clock: FakeClock) -> None:
    cache = cache_factory(clock=clock)
    assert await cache.add("k", "first") is True
    assert await cache.add("k", "second") is False
    assert await cache.get("k") == "first"


async def test_add_after_expiry_succeeds(
    cache_factory: Callable[..., AsyncCache],
    clock: FakeClock,
) -> None:
    cache = cache_factory(clock=clock)
    assert await cache.add("k", "v", ttl=5) is True
    clock.tick(6)
    assert await cache.add("k", "v2", ttl=5) is True
    assert await cache.get("k") == "v2"


async def test_incr_creates_and_increments(
    cache_factory: Callable[..., AsyncCache],
    clock: FakeClock,
) -> None:
    cache = cache_factory(clock=clock)
    assert await cache.incr("counter") == 1
    assert await cache.incr("counter") == 2
    assert await cache.incr("counter", amount=10) == 12


async def test_incr_concurrent_safety(
    cache_factory: Callable[..., AsyncCache],
    clock: FakeClock,
) -> None:
    cache = cache_factory(clock=clock)
    await asyncio.gather(*[cache.incr("counter") for _ in range(100)])
    assert await cache.get("counter") == 100


async def test_incr_on_non_int_raises(
    cache_factory: Callable[..., AsyncCache],
    clock: FakeClock,
) -> None:
    cache = cache_factory(clock=clock)
    await cache.set("k", "not-an-int")
    with pytest.raises(TypeError):
        await cache.incr("k")


async def test_delete(cache_factory: Callable[..., AsyncCache], clock: FakeClock) -> None:
    cache = cache_factory(clock=clock)
    await cache.set("k", "v")
    await cache.delete("k")
    assert await cache.get("k") is None
    # Delete is a no-op on missing keys.
    await cache.delete("absent")


async def test_health_check(cache_factory: Callable[..., AsyncCache], clock: FakeClock) -> None:
    cache = cache_factory(clock=clock)
    snap = await cache.health_check()
    assert snap.healthy is True
    assert snap.backend == cache_factory.backend  # type: ignore[attr-defined]
