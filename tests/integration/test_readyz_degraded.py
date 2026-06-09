"""Integration test for ``/readyz`` reporting under a degraded Redis (ROADMAP M4 exit gate).

Spins ``testcontainers-redis``, registers a :class:`RedisAsyncCache`
with the kit's recovery roster, then pauses the container via the
Docker SDK (so the host port stays stable) and asserts the
:func:`health_snapshot` aggregator reports
``degraded-but-serving``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("redis")
pytest.importorskip("testcontainers.redis")

from resilience_kit.cache.redis_impl import RedisAsyncCache
from resilience_kit.health import HealthStatus, health_snapshot
from resilience_kit.recovery import register_for_recovery, reset_recovery_state

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_cache(redis_container: object) -> AsyncIterator[RedisAsyncCache]:
    """Build a RedisAsyncCache against the session container."""
    reset_recovery_state()
    url = (
        f"redis://{redis_container.get_container_host_ip()}:"  # type: ignore[attr-defined]
        f"{redis_container.get_exposed_port(6379)}/0"  # type: ignore[attr-defined]
    )
    from redis.asyncio import Redis  # noqa: PLC0415

    client = Redis.from_url(url, decode_responses=False)
    cache = RedisAsyncCache(redis_client=client, alias="default")
    register_for_recovery(cache)
    try:
        yield cache
    finally:
        await client.aclose()
        reset_recovery_state()


@pytest.mark.asyncio
async def test_readyz_ok_when_redis_alive(
    redis_cache: RedisAsyncCache,
) -> None:
    """Baseline: healthy redis → ``status=ok``."""
    agg = await health_snapshot(probe_timeout=1.0)
    assert agg.status is HealthStatus.OK
    assert agg.http_status == 200


@pytest.mark.asyncio
async def test_readyz_degraded_when_redis_paused(
    redis_container: object,
    redis_cache: RedisAsyncCache,
) -> None:
    """Exit-gate: pausing redis → ``degraded`` (or ``degraded_but_serving``)."""
    import docker  # noqa: PLC0415

    client = docker.from_env()
    container_id = redis_container.get_wrapped_container().id  # type: ignore[attr-defined]
    container = client.containers.get(container_id)
    container.pause()
    try:
        agg = await health_snapshot(probe_timeout=0.5)
        assert agg.status is not HealthStatus.OK
        # Single-backend deploy ⇒ no healthy peer ⇒ `degraded`. Multi-
        # backend deploys (cache + breaker + throttle) would land on
        # `degraded_but_serving`.
        assert agg.snapshots[0].healthy is False
    finally:
        container.unpause()
