"""Shared Redis client ownership — #D1 (ADR-0017).

Every Redis-backed subsystem must share **one** ``redis.asyncio.Redis`` per
URL, built once and closed explicitly. These tests force the outage-free build
path with a counting ``from_url`` stub, so no live Redis is required.
"""

from __future__ import annotations

import pytest

pytest.importorskip("redis")

import redis.asyncio

from resilience_kit import _redis
from resilience_kit.cache.provider import get_cache
from resilience_kit.circuit_breaker.base import BreakerConfig
from resilience_kit.circuit_breaker.provider import get_breaker
from resilience_kit.throttle.provider import get_throttle

_URL = "redis://localhost:6379/0"


class _FakeClient:
    """Minimal stand-in for ``redis.asyncio.Redis``; records ``aclose``."""

    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


@pytest.fixture
def counting_from_url(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Patch ``Redis.from_url`` to count builds and return fresh fakes.

    Returns the single-element call counter; ``monkeypatch`` reverts the
    patch at teardown, so the fixture needs no teardown of its own.
    """
    calls = [0]

    def _factory(url: str, *_a: object, **_k: object) -> _FakeClient:
        calls[0] += 1
        return _FakeClient()

    monkeypatch.setattr(redis.asyncio.Redis, "from_url", staticmethod(_factory))
    return calls


def test_get_redis_client_memoises_per_url(counting_from_url: list[int]) -> None:
    """Two calls for the same URL build once and return the same instance."""
    first = _redis.get_redis_client(_URL)
    second = _redis.get_redis_client(_URL)
    assert first is second
    assert counting_from_url[0] == 1


def test_distinct_urls_build_distinct_clients(counting_from_url: list[int]) -> None:
    a = _redis.get_redis_client(_URL)
    b = _redis.get_redis_client("redis://localhost:6379/1")
    assert a is not b
    assert counting_from_url[0] == 2


@pytest.mark.asyncio
async def test_aclose_closes_and_clears(counting_from_url: list[int]) -> None:
    """``aclose_redis_clients`` closes each client and forces a rebuild after."""
    client = _redis.get_redis_client(_URL)
    await _redis.aclose_redis_clients()
    assert client.closed == 1  # type: ignore[attr-defined]
    # Cache cleared: next build mints a fresh client.
    rebuilt = _redis.get_redis_client(_URL)
    assert rebuilt is not client
    assert counting_from_url[0] == 2


def test_reset_drops_references_without_awaiting(counting_from_url: list[int]) -> None:
    client = _redis.get_redis_client(_URL)
    _redis.reset_redis_clients()
    assert client.closed == 0  # type: ignore[attr-defined]  # not awaited, just dropped
    assert _redis.get_redis_client(_URL) is not client


def test_all_three_backends_share_one_client(
    counting_from_url: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Breaker, cache, and throttle for one URL share a single pooled client."""
    monkeypatch.setenv("RESILIENCE_REDIS_URL", _URL)
    monkeypatch.setenv("RESILIENCE_BACKEND", "redis")
    from resilience_kit.runtime import reset_settings_cache  # noqa: PLC0415

    reset_settings_cache()

    breaker = get_breaker(name="svc", config=BreakerConfig())
    cache = get_cache("default")
    throttle = get_throttle()

    assert breaker._redis is cache._redis  # type: ignore[attr-defined]
    assert cache._redis is throttle._redis  # type: ignore[attr-defined]
    assert counting_from_url[0] == 1
