"""Process-wide Redis client ownership.

Every Redis-backed subsystem (cache / breaker / throttle) needs an
``redis.asyncio.Redis``. Historically each provider called
``Redis.from_url(settings.redis_url)`` on first build, so a process ran three
independent connection pools and re-registering a service leaked the previous
client (nothing ever called ``aclose``).

This module centralises that: one client **per URL**, built lazily, shared by
all subsystems, and closed explicitly on shutdown. See ADR-0017.

The ``redis`` import stays lazy (guarded by the ``[redis]`` extra) — importing
this module does not require ``redis`` to be installed.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


_lock = threading.Lock()
_clients: dict[str, Redis] = {}


def get_redis_client(url: str) -> Redis:
    """Return the process-wide ``redis.asyncio.Redis`` for ``url``.

    Built once per URL and cached; all subsystems sharing the same URL share
    one connection pool. Thread-safe.

    Args:
        url: The Redis/Valkey connection URL (``settings.redis_url``).

    Returns:
        The shared client for ``url``.
    """
    existing = _clients.get(url)
    if existing is not None:
        return existing
    from redis.asyncio import Redis  # noqa: PLC0415 — guarded by the [redis] extra

    with _lock:
        client = _clients.get(url)
        if client is None:
            client = Redis.from_url(url)
            _clients[url] = client
        return client


async def aclose_redis_clients() -> None:
    """Close every shared client and clear the cache.

    Called from adapter shutdown (FastAPI lifespan exit, Django daemon-loop
    teardown) and :func:`resilience_kit.testing.reset.reset_all_singletons_async`.
    Safe to call when no clients were ever built.
    """
    with _lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        aclose = getattr(client, "aclose", None)
        if aclose is not None:
            await aclose()


def reset_redis_clients() -> None:
    """Drop client references without awaiting. Sync test hook.

    The async ``aclose`` cannot run from the sync
    :func:`resilience_kit.testing.reset.reset_all_singletons`; test suites own
    their Redis fixtures (fakeredis / testcontainers) and tear the connections
    down themselves, so dropping references here is sufficient to force a fresh
    client on the next build.
    """
    with _lock:
        _clients.clear()
