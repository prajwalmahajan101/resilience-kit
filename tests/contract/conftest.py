"""Backend factory fixtures for the contract suite.

Each fixture returns a callable that builds a primitive of the named backend
type. M1 wires only ``memory``; M2 extends the ``params`` lists in place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resilience_kit.cache.memory_impl import InMemoryAsyncCache
from resilience_kit.circuit_breaker.memory_impl import InMemoryAsyncBreaker
from resilience_kit.testing import FakeClock, reset_all_singletons
from resilience_kit.throttle.memory_impl import InMemoryAsyncThrottle

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from resilience_kit.cache.base import AsyncCache
    from resilience_kit.circuit_breaker.base import AsyncBreaker, BreakerConfig
    from resilience_kit.throttle.base import AsyncThrottle


@pytest.fixture(autouse=True)
def _reset_kit_singletons() -> Iterator[None]:
    """Reset every kit-managed singleton between tests."""
    reset_all_singletons()
    yield
    reset_all_singletons()


@pytest.fixture
def clock() -> FakeClock:
    """Return a fresh :class:`FakeClock`."""
    return FakeClock()


@pytest.fixture(params=["memory"])
def breaker_factory(
    request: pytest.FixtureRequest,
) -> Callable[..., AsyncBreaker]:
    """Return a callable that builds a breaker of the parametrized backend."""
    backend = request.param

    def make(
        name: str = "svc",
        config: BreakerConfig | None = None,
        *,
        clock: FakeClock | None = None,
    ) -> AsyncBreaker:
        if backend == "memory":
            return InMemoryAsyncBreaker(name=name, config=config, clock=clock)
        raise NotImplementedError(f"backend {backend!r} not wired yet")

    make.backend = backend  # type: ignore[attr-defined]
    return make


@pytest.fixture(params=["memory"])
def throttle_factory(
    request: pytest.FixtureRequest,
) -> Callable[..., AsyncThrottle]:
    """Return a callable that builds a throttle of the parametrized backend."""
    backend = request.param

    def make(*, clock: FakeClock | None = None) -> AsyncThrottle:
        if backend == "memory":
            return InMemoryAsyncThrottle(clock=clock)
        raise NotImplementedError(f"backend {backend!r} not wired yet")

    make.backend = backend  # type: ignore[attr-defined]
    return make


@pytest.fixture(params=["memory"])
def cache_factory(
    request: pytest.FixtureRequest,
) -> Callable[..., AsyncCache]:
    """Return a callable that builds a cache of the parametrized backend."""
    backend = request.param

    def make(*, clock: FakeClock | None = None) -> AsyncCache:
        if backend == "memory":
            return InMemoryAsyncCache(clock=clock)
        raise NotImplementedError(f"backend {backend!r} not wired yet")

    make.backend = backend  # type: ignore[attr-defined]
    return make
