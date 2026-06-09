"""Exit-gate integration test — recovery monitor flips back in <5s.

Requires Docker / testcontainers. Marked ``integration``; runs in the
dedicated ``integration.yml`` workflow, not the lightweight CI matrix.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from resilience_kit import registry
from resilience_kit.recovery import attempt_recover_all
from resilience_kit.runtime import set_settings_source
from resilience_kit.settings import ResilienceSettings


@pytest.mark.integration
async def test_recovery_under_5s(redis_url: str, redis_container: object) -> None:
    """Backend recovers within the exit-gate window after Redis returns.

    Args:
        redis_url: testcontainers-provided Redis URL.
        redis_container: the container handle (start/stop control).
    """
    settings = ResilienceSettings(
        backend="redis",
        redis_url=redis_url,
    )
    settings.recovery.probe_interval_seconds = 0.2

    class FixedSource:
        def load(self) -> ResilienceSettings:
            return settings

    set_settings_source(FixedSource())

    breaker = registry.get_breaker("svc")
    snap = await breaker.health_check()
    assert snap.backend == "redis", snap

    # Pause the container (TCP frozen, port mapping preserved). Stopping
    # would reassign the port and break the connection pool's host:port.
    docker_client = redis_container.get_docker_client()  # type: ignore[attr-defined]
    container_id = redis_container.get_wrapped_container().id  # type: ignore[attr-defined]
    docker_client.client.api.pause(container_id)
    try:

        async def noop() -> str:
            return "ok"

        # Fail-open: in-memory fallback handles the call.
        assert await breaker.call(noop) == "ok"
        assert (await breaker.health_check()).healthy is False
    finally:
        docker_client.client.api.unpause(container_id)

    start = time.monotonic()
    while time.monotonic() - start < 5.0:
        if await attempt_recover_all() > 0:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("recovery did not happen within 5s")

    assert (await breaker.health_check()).healthy is True
