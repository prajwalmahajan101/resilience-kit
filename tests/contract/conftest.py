"""Backend factory fixtures for the contract suite.

Each fixture returns a callable that builds a primitive of the named
backend type. ``memory`` always runs; ``pybreaker`` always runs (it's an
in-process backend); ``redis`` runs only when a Redis container can be
spun up via testcontainers + Docker. Tests that need a particular backend
are auto-skipped when the prerequisite is missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resilience_kit.cache.memory_impl import InMemoryAsyncCache
from resilience_kit.circuit_breaker.memory_impl import InMemoryAsyncBreaker
from resilience_kit.circuit_breaker.pybreaker_impl import PyBreakerAsyncBreaker
from resilience_kit.testing import FakeClock, reset_all_singletons
from resilience_kit.throttle.memory_impl import InMemoryAsyncThrottle

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from resilience_kit.cache.base import AsyncCache
    from resilience_kit.circuit_breaker.base import AsyncBreaker, BreakerConfig
    from resilience_kit.throttle.base import AsyncThrottle


@pytest.fixture(autouse=True)
def _reset_kit_singletons() -> Iterator[None]:
    """Reset every kit-managed singleton between tests."""
    reset_all_singletons()
    yield
    reset_all_singletons()


@pytest.fixture(autouse=True)
async def _flush_redis(session_redis_url: str | None) -> AsyncIterator[None]:
    """Flush the shared session Redis between tests so state doesn't leak.

    Args:
        session_redis_url: Session Redis URL (or ``None`` to no-op).
    """
    if session_redis_url is None:
        yield
        return
    from redis.asyncio import Redis  # noqa: PLC0415

    client = Redis.from_url(session_redis_url)
    try:
        await client.flushdb()
        yield
        await client.flushdb()
    finally:
        await client.aclose()


@pytest.fixture
def clock() -> FakeClock:
    """Return a fresh :class:`FakeClock`."""
    return FakeClock()


def _require_redis() -> str | None:
    """Return a Redis URL via testcontainers, or ``None`` to skip.

    Returns:
        Connection URL on success; ``None`` when Docker / testcontainers
        unavailable.
    """
    try:
        from testcontainers.redis import RedisContainer  # noqa: PLC0415
    except ImportError:
        return None
    try:
        container = RedisContainer("redis:7")
        container.start()
    except Exception:
        return None
    # Pin lifetime to the session via pytest-side caching.
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6379)
    # Stash the container so it isn't GC'd mid-test.
    _require_redis._container = container  # type: ignore[attr-defined]
    return f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def session_redis_url() -> str | None:
    """Session-scoped Redis URL (or ``None`` to skip redis-parametrized tests)."""
    return _require_redis()


@pytest.fixture(params=["memory", "pybreaker", "redis"])
def breaker_factory(
    request: pytest.FixtureRequest,
    session_redis_url: str | None,
) -> Callable[..., AsyncBreaker]:
    """Return a callable that builds a breaker of the parametrized backend.

    Args:
        request: Pytest request object.
        session_redis_url: Session Redis URL (or ``None`` to skip).

    Returns:
        Factory callable.
    """
    backend = request.param
    if backend == "redis" and session_redis_url is None:
        pytest.skip("No Redis available for the contract suite")

    def make(
        name: str = "svc",
        config: BreakerConfig | None = None,
        *,
        clock: FakeClock | None = None,
    ) -> AsyncBreaker:
        if backend == "memory":
            return InMemoryAsyncBreaker(name=name, config=config, clock=clock)
        if backend == "pybreaker":
            return PyBreakerAsyncBreaker(name=name, config=config)
        if backend == "redis":
            from redis.asyncio import Redis  # noqa: PLC0415

            from resilience_kit.circuit_breaker.redis_impl import (  # noqa: PLC0415
                RedisAsyncBreaker,
            )

            assert session_redis_url is not None
            client = Redis.from_url(session_redis_url)
            return RedisAsyncBreaker(
                name=name,
                config=config,
                redis_client=client,
                clock=clock,
            )
        raise NotImplementedError(backend)

    make.backend = backend  # type: ignore[attr-defined]
    return make


@pytest.fixture(params=["memory", "redis"])
def throttle_factory(
    request: pytest.FixtureRequest,
    session_redis_url: str | None,
) -> Callable[..., AsyncThrottle]:
    """Return a callable that builds a throttle of the parametrized backend.

    Args:
        request: Pytest request object.
        session_redis_url: Session Redis URL (or ``None`` to skip).

    Returns:
        Factory callable.
    """
    backend = request.param
    if backend == "redis" and session_redis_url is None:
        pytest.skip("No Redis available for the contract suite")

    def make(*, clock: FakeClock | None = None) -> AsyncThrottle:
        if backend == "memory":
            return InMemoryAsyncThrottle(clock=clock)
        if backend == "redis":
            from redis.asyncio import Redis  # noqa: PLC0415

            from resilience_kit.throttle.redis_impl import RedisAsyncThrottle  # noqa: PLC0415

            assert session_redis_url is not None
            client = Redis.from_url(session_redis_url)
            return RedisAsyncThrottle(redis_client=client, clock=clock)
        raise NotImplementedError(backend)

    make.backend = backend  # type: ignore[attr-defined]
    return make


@pytest.fixture(params=["memory", "redis"])
def cache_factory(
    request: pytest.FixtureRequest,
    session_redis_url: str | None,
) -> Callable[..., AsyncCache]:
    """Return a callable that builds a cache of the parametrized backend.

    Args:
        request: Pytest request object.
        session_redis_url: Session Redis URL (or ``None`` to skip).

    Returns:
        Factory callable.
    """
    backend = request.param
    if backend == "redis" and session_redis_url is None:
        pytest.skip("No Redis available for the contract suite")

    def make(*, clock: FakeClock | None = None) -> AsyncCache:
        if backend == "memory":
            return InMemoryAsyncCache(clock=clock)
        if backend == "redis":
            from redis.asyncio import Redis  # noqa: PLC0415

            from resilience_kit.cache.redis_impl import RedisAsyncCache  # noqa: PLC0415

            assert session_redis_url is not None
            client = Redis.from_url(session_redis_url, decode_responses=True)
            return RedisAsyncCache(redis_client=client, clock=clock)
        raise NotImplementedError(backend)

    make.backend = backend  # type: ignore[attr-defined]
    return make
