"""Circuit-breaker backend provider — entry-point + settings-string + builtin resolution.

The resolution chain (LLD §3) is implemented by
:func:`resilience_kit._providers.resolve_provider`. This module simply
declares the breaker-specific builtins and the ``auto`` policy.

``auto`` (default): picks ``redis`` when ``settings.redis_url`` is set and
``redis`` extra is importable; else falls back to ``memory``. The decision
is made once on first call; tests / adapters can override via
``RESILIENCE_BACKEND``.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

from resilience_kit._providers import resolve_provider
from resilience_kit.circuit_breaker.memory_impl import InMemoryAsyncBreaker
from resilience_kit.circuit_breaker.pybreaker_impl import PyBreakerAsyncBreaker
from resilience_kit.runtime import get_settings

if TYPE_CHECKING:
    from resilience_kit.circuit_breaker.base import AsyncBreaker, BreakerConfig
    from resilience_kit.testing.fakes import Clock


_ENTRY_POINT_GROUP = "resilience_kit.breaker_backends"


def _build_memory(
    *,
    name: str,
    config: BreakerConfig,
    clock: Clock | None = None,
) -> AsyncBreaker:
    return InMemoryAsyncBreaker(name=name, config=config, clock=clock)


def _build_pybreaker(
    *,
    name: str,
    config: BreakerConfig,
    **_: object,
) -> AsyncBreaker:
    return PyBreakerAsyncBreaker(name=name, config=config)


def _build_redis(
    *,
    name: str,
    config: BreakerConfig,
    clock: Clock | None = None,
) -> AsyncBreaker:
    """Build a Redis-backed breaker.

    Args:
        name: Service identifier.
        config: Per-breaker config.
        clock: Injectable clock.

    Returns:
        A Redis-backed breaker.

    Raises:
        ValueError: ``redis_url`` is not configured.
    """
    settings = get_settings()
    if not settings.redis_url:
        raise ValueError(
            "Cannot build a redis breaker without RESILIENCE_REDIS_URL. "
            "Set RESILIENCE_BACKEND=memory to avoid this.",
        )
    from redis.asyncio import Redis  # noqa: PLC0415 — guarded by extra

    from resilience_kit.circuit_breaker.redis_impl import RedisAsyncBreaker  # noqa: PLC0415
    from resilience_kit.recovery import register_for_recovery  # noqa: PLC0415

    client = Redis.from_url(settings.redis_url)
    breaker = RedisAsyncBreaker(
        name=name,
        config=config,
        redis_client=client,
        clock=clock,
    )
    register_for_recovery(breaker)
    return breaker


def _resolve_auto() -> str:
    """Pick ``redis`` or ``memory`` based on settings."""
    settings = get_settings()
    if settings.redis_url and importlib.util.find_spec("redis.asyncio") is not None:
        return "redis"
    return "memory"


_BUILTINS = {
    "memory": _build_memory,
    "pybreaker": _build_pybreaker,
    "redis": _build_redis,
}


def get_breaker(
    *,
    name: str,
    config: BreakerConfig,
    clock: Clock | None = None,
) -> AsyncBreaker:
    """Return a breaker instance for ``name`` using the configured backend.

    Resolution: settings ``backend`` field → entry point → builtin → fail.
    The special value ``auto`` resolves to ``redis`` or ``memory`` based
    on availability.

    Args:
        name: Service identifier.
        config: Per-breaker config.
        clock: Injectable clock — for tests.

    Returns:
        A breaker instance.
    """
    backend_name: str = get_settings().backend
    if backend_name == "auto":
        backend_name = _resolve_auto()
    return resolve_provider(
        group=_ENTRY_POINT_GROUP,
        name=backend_name,
        builtins=_BUILTINS,
        factory_kwargs={"name": name, "config": config, "clock": clock},
    )
