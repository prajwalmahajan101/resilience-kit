"""Unit tests for the cache provider singleton (:mod:`resilience_kit.cache.provider`).

``get_cache`` is the documented public entry point for the cache
subsystem (PRD §5.3, the boilerplate migration guide). These tests pin
its singleton-per-alias behaviour and the ``reset_cache`` test hook.
"""

from __future__ import annotations

from resilience_kit.cache.memory_impl import InMemoryAsyncCache
from resilience_kit.cache.provider import get_cache, reset_cache


def test_get_cache_returns_memory_backend_by_default() -> None:
    """With no Redis configured, ``auto`` resolves to the in-memory backend."""
    cache = get_cache()
    assert isinstance(cache, InMemoryAsyncCache)


def test_get_cache_is_singleton_per_alias() -> None:
    """Repeat calls for one alias return the same instance; aliases differ."""
    first = get_cache("default")
    assert get_cache("default") is first
    assert get_cache("other") is not first


def test_reset_cache_drops_cached_instances() -> None:
    """``reset_cache`` clears the per-alias cache so the next call rebuilds."""
    first = get_cache("default")
    reset_cache()
    assert get_cache("default") is not first
