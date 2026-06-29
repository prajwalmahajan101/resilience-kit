"""Throttle fail-mode under a Redis outage — #B8.

When Redis is unreachable the throttle either fails *open* (degrades to a
per-pod in-memory window — the default) or fails *closed* (denies every
request — hard-limit safety). These unit tests force the outage with a dead
Redis stub, so no live Redis is required.
"""

from __future__ import annotations

import pytest

pytest.importorskip("redis")

from redis.exceptions import ConnectionError as RedisConnectionError

from resilience_kit.throttle.base import Rate
from resilience_kit.throttle.redis_impl import RedisAsyncThrottle


class _DeadRedis:
    """A Redis client whose every call raises ``RedisError``."""

    async def script_load(self, _script: str) -> str:
        raise RedisConnectionError("redis is down")

    async def evalsha(self, *_args: object) -> object:
        raise RedisConnectionError("redis is down")

    async def ping(self) -> object:
        raise RedisConnectionError("redis is down")

    async def delete(self, *_args: object) -> object:
        raise RedisConnectionError("redis is down")


@pytest.mark.asyncio
async def test_fail_open_degrades_to_in_memory() -> None:
    """Default fail_mode='open' admits via the per-pod in-memory fallback."""
    throttle = RedisAsyncThrottle(redis_client=_DeadRedis(), fail_mode="open")
    rate = Rate(count=2, per_seconds=60)

    first = await throttle.check("k", rate)
    second = await throttle.check("k", rate)
    third = await throttle.check("k", rate)

    # The in-memory fallback enforces the limit locally: 2 admitted, 3rd denied.
    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False


@pytest.mark.asyncio
async def test_fail_closed_denies_while_degraded() -> None:
    """fail_mode='closed' denies every request during a Redis outage."""
    throttle = RedisAsyncThrottle(redis_client=_DeadRedis(), fail_mode="closed")
    rate = Rate(count=100, per_seconds=60)

    decision = await throttle.check("k", rate)

    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.limit == rate.count
    assert decision.reset_after == rate.per_seconds
