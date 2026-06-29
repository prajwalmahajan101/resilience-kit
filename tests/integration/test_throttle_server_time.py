"""Server-side throttle clock — #B5.

The sliding-window Lua reads ``now`` from ``redis.call('TIME')`` rather than
from the client. Two pods with divergent client clocks must therefore enforce
the *same* window against a shared Redis — client clock skew can no longer
over- or under-throttle the fleet.

Requires Docker (testcontainers Redis); skipped otherwise.
"""

from __future__ import annotations

import pytest

from resilience_kit.testing import FakeClock
from resilience_kit.throttle import Rate

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_redis_throttle_ignores_client_clock_skew(redis_url: str) -> None:
    """Two pods with wildly different client clocks share one window.

    Pre-#B5 each pod passed its own ``clock.now()`` as the Lua's ``now``, so a
    skewed pod computed a different cutoff and the shared sliding window broke.
    With server-side ``TIME`` the decision is independent of the client clock:
    across both pods exactly ``rate.count`` requests are admitted, not double.
    """
    from redis.asyncio import Redis  # noqa: PLC0415

    from resilience_kit.throttle.redis_impl import RedisAsyncThrottle  # noqa: PLC0415

    rate = Rate(count=4, per_seconds=60)
    key = "b5-skew-test"

    client_a = Redis.from_url(redis_url)
    client_b = Redis.from_url(redis_url)
    # Clocks ~250 years apart — far beyond any realistic NTP drift.
    pod_a = RedisAsyncThrottle(redis_client=client_a, clock=FakeClock(start=1_000_000.0))
    pod_b = RedisAsyncThrottle(
        redis_client=client_b,
        clock=FakeClock(start=9_000_000_000.0),
    )

    try:
        await pod_a.reset(key)

        allowed = 0
        # Alternate across the two skewed pods against the same key.
        for pod in (pod_a, pod_b, pod_a, pod_b, pod_a, pod_b, pod_a, pod_b):
            if (await pod.check(key, rate)).allowed:
                allowed += 1

        # Exactly the shared limit — not 8 (which a per-pod clock would allow).
        assert allowed == rate.count
    finally:
        await client_a.aclose()
        await client_b.aclose()
