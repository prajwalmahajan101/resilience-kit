"""Throttle backend provider — chain-resolved (LLD §3)."""

from __future__ import annotations

import importlib.util
import logging
from typing import TYPE_CHECKING

from resilience_kit._providers import resolve_provider
from resilience_kit.runtime import get_settings
from resilience_kit.throttle.memory_impl import InMemoryAsyncThrottle

if TYPE_CHECKING:
    from resilience_kit.testing.fakes import Clock
    from resilience_kit.throttle.base import AsyncThrottle


_logger = logging.getLogger(__name__)
_ENTRY_POINT_GROUP = "resilience_kit.throttle_backends"


def _build_memory(*, clock: Clock | None = None) -> AsyncThrottle:
    return InMemoryAsyncThrottle(clock=clock)


def _build_redis(*, clock: Clock | None = None) -> AsyncThrottle:
    """Build a Redis-backed throttle.

    Args:
        clock: Injectable clock.

    Returns:
        A Redis-backed throttle.

    Raises:
        ValueError: ``redis_url`` is not configured.
    """
    settings = get_settings()
    if not settings.redis_url:
        raise ValueError("Cannot build a redis throttle without RESILIENCE_REDIS_URL.")
    from redis.asyncio import Redis  # noqa: PLC0415

    from resilience_kit.recovery import register_for_recovery  # noqa: PLC0415
    from resilience_kit.throttle.redis_impl import RedisAsyncThrottle  # noqa: PLC0415

    client = Redis.from_url(settings.redis_url)
    throttle = RedisAsyncThrottle(redis_client=client, clock=clock)
    register_for_recovery(throttle)
    return throttle


def _resolve_auto() -> str:
    settings = get_settings()
    if settings.redis_url and importlib.util.find_spec("redis.asyncio") is not None:
        return "redis"
    return "memory"


_BUILTINS = {
    "memory": _build_memory,
    "redis": _build_redis,
}


_default: AsyncThrottle | None = None


def get_throttle(*, clock: Clock | None = None) -> AsyncThrottle:
    """Return the process-wide throttle singleton.

    Args:
        clock: Injectable clock — used only on first build.

    Returns:
        The throttle singleton.
    """
    global _default  # noqa: PLW0603
    if _default is not None:
        return _default
    backend_name: str = get_settings().backend
    if backend_name == "auto":
        backend_name = _resolve_auto()
    _default = resolve_provider(
        group=_ENTRY_POINT_GROUP,
        name=backend_name,
        builtins=_BUILTINS,
        factory_kwargs={"clock": clock},
    )
    return _default


def reset_throttle() -> None:
    """Drop the cached throttle. Test hook."""
    global _default  # noqa: PLW0603
    _default = None
