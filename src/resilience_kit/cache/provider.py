"""Cache backend provider — chain-resolved (LLD §3)."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

from resilience_kit._providers import resolve_provider
from resilience_kit.cache.memory_impl import InMemoryAsyncCache
from resilience_kit.runtime import get_settings

if TYPE_CHECKING:
    from resilience_kit.cache.base import AsyncCache
    from resilience_kit.testing.fakes import Clock


_ENTRY_POINT_GROUP = "resilience_kit.cache_backends"


def _build_memory(*, alias: str = "default", clock: Clock | None = None) -> AsyncCache:
    del alias  # alias only meaningful for backends that namespace per-alias
    return InMemoryAsyncCache(clock=clock)


def _build_redis(*, alias: str = "default", clock: Clock | None = None) -> AsyncCache:
    """Build a Redis-backed cache.

    Args:
        alias: Logical cache name.
        clock: Injectable clock.

    Returns:
        A Redis-backed cache.

    Raises:
        ValueError: ``redis_url`` is not configured.
    """
    settings = get_settings()
    if not settings.redis_url:
        raise ValueError("Cannot build a redis cache without RESILIENCE_REDIS_URL.")
    from redis.asyncio import Redis  # noqa: PLC0415

    from resilience_kit.cache.redis_impl import RedisAsyncCache  # noqa: PLC0415
    from resilience_kit.recovery import register_for_recovery  # noqa: PLC0415

    client = Redis.from_url(settings.redis_url)
    cache = RedisAsyncCache(redis_client=client, alias=alias, clock=clock)
    register_for_recovery(cache)
    return cache


def _resolve_auto() -> str:
    settings = get_settings()
    if settings.redis_url and importlib.util.find_spec("redis.asyncio") is not None:
        return "redis"
    return "memory"


_BUILTINS = {
    "memory": _build_memory,
    "redis": _build_redis,
}


_caches: dict[str, AsyncCache] = {}


def get_cache(alias: str = "default", *, clock: Clock | None = None) -> AsyncCache:
    """Return the cache for ``alias``, building it on first call.

    Args:
        alias: Cache alias.
        clock: Injectable clock — used only when the alias is first built.

    Returns:
        The cache for ``alias``.
    """
    cached = _caches.get(alias)
    if cached is not None:
        return cached
    backend_name: str = get_settings().backend
    if backend_name == "auto":
        backend_name = _resolve_auto()
    cached = resolve_provider(
        group=_ENTRY_POINT_GROUP,
        name=backend_name,
        builtins=_BUILTINS,
        factory_kwargs={"alias": alias, "clock": clock},
    )
    _caches[alias] = cached
    return cached


def reset_cache() -> None:
    """Drop all cached caches. Test hook."""
    _caches.clear()
