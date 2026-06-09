"""Cache backend provider — M1 returns the in-memory backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from resilience_kit.cache.memory_impl import InMemoryAsyncCache

if TYPE_CHECKING:
    from resilience_kit.cache.base import AsyncCache
    from resilience_kit.testing.fakes import Clock


_caches: dict[str, AsyncCache] = {}


def get_cache(alias: str = "default", *, clock: Clock | None = None) -> AsyncCache:
    """Return the cache for ``alias``, building it on first call.

    At M1 always returns an in-memory cache. M2 introduces provider-chain
    resolution.

    Args:
        alias: Cache alias (multiple named caches are supported).
        clock: Injectable clock — used only when the alias is first built.

    Returns:
        The cache for ``alias``.
    """
    cached = _caches.get(alias)
    if cached is None:
        cached = InMemoryAsyncCache(clock=clock)
        _caches[alias] = cached
    return cached


def reset_cache() -> None:
    """Drop all cached caches. Test hook."""
    _caches.clear()
