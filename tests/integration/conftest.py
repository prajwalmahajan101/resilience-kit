"""Integration fixtures — testcontainers-backed Redis / Valkey.

Tests in this folder are marked ``integration`` and skipped unless Docker
is reachable. The default contract suite under ``tests/contract/`` runs in
the lightweight CI matrix; this folder runs in the dedicated
``integration.yml`` workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resilience_kit.testing import reset_all_singletons

if TYPE_CHECKING:
    from collections.abc import Iterator


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_kit_singletons() -> Iterator[None]:
    """Reset every kit-managed singleton between tests."""
    reset_all_singletons()
    yield
    reset_all_singletons()


@pytest.fixture(scope="session")
def redis_container() -> Iterator[object]:
    """Spin a Redis container for the session.

    Yields:
        The running container (so individual tests can stop/start it for
        recovery-monitor exercises).
    """
    try:
        from testcontainers.redis import RedisContainer  # noqa: PLC0415
    except ImportError:
        pytest.skip("testcontainers[redis] not installed; skipping integration tests")

    container = RedisContainer("redis:7")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture
def redis_url(redis_container: object) -> str:
    """Return a connection URL for the running Redis container.

    Args:
        redis_container: Session-scoped Redis container.

    Returns:
        ``redis://host:port/0``.
    """
    host = redis_container.get_container_host_ip()  # type: ignore[attr-defined]
    port = redis_container.get_exposed_port(6379)  # type: ignore[attr-defined]
    return f"redis://{host}:{port}/0"
