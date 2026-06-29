"""In-process async cache — dict + monotonic-clock expiry.

Lazy eviction — expired entries are dropped on next read for the same key.
For long-lived processes with many short-lived keys, callers should call
:meth:`InMemoryAsyncCache.delete` explicitly; an active sweeper would add
complexity without buying much (the Redis backend in M2 is the production
path).
"""

from __future__ import annotations

import asyncio
from typing import Any

from resilience_kit.circuit_breaker.base import HealthSnapshot
from resilience_kit.testing.fakes import Clock, SystemClock


class InMemoryAsyncCache:
    """In-process async cache.

    Stored shape: ``{key: (value, expires_at_monotonic_or_None)}``.
    """

    def __init__(self, clock: Clock | None = None, *, alias: str | None = None) -> None:
        """Initialise an empty cache.

        Args:
            clock: Injectable clock — for tests.
            alias: Accepted and ignored. The provider chain resolves the
                kit's ``memory`` entry point to this class directly and
                passes ``alias`` (meaningful only for backends that
                namespace per alias, like Redis). Accepting it here keeps
                ``cache.provider.get_cache(alias=...)`` working when the
                entry point shadows the ``_build_memory`` adapter.
        """
        del alias  # only meaningful for per-alias-namespaced backends
        self._clock: Clock = clock or SystemClock()
        self._lock = asyncio.Lock()
        self._store: dict[str, tuple[Any, float | None]] = {}

    async def get(self, key: str) -> Any | None:
        """Return the value at ``key``, or ``None`` if missing or expired.

        Args:
            key: Cache key.

        Returns:
            Stored value, or ``None``.
        """
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires = entry
            if expires is not None and self._clock.monotonic() >= expires:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set ``key`` → ``value``, expiring after ``ttl`` seconds.

        Args:
            key: Cache key.
            value: Value to store.
            ttl: TTL in seconds; ``None`` means no expiry.
        """
        async with self._lock:
            self._store[key] = (value, self._expires(ttl))

    async def add(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set ``key`` only if it does not exist.

        Args:
            key: Cache key.
            value: Value to store.
            ttl: TTL in seconds.

        Returns:
            ``True`` if created, ``False`` if it already existed (and was not expired).
        """
        async with self._lock:
            existing = self._store.get(key)
            if existing is not None:
                _, expires = existing
                if expires is None or self._clock.monotonic() < expires:
                    return False
            self._store[key] = (value, self._expires(ttl))
            return True

    async def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        """Atomically increment ``key`` by ``amount``.

        Args:
            key: Cache key.
            amount: Increment delta.
            ttl: TTL applied only when the key is being created from absent.

        Returns:
            New value after increment.

        Raises:
            TypeError: The existing value is not an ``int``.
        """
        async with self._lock:
            entry = self._store.get(key)
            existing_expires: float | None
            if entry is None:
                base = 0
                existing_expires = self._expires(ttl)
            else:
                current, existing_expires = entry
                if existing_expires is not None and self._clock.monotonic() >= existing_expires:
                    base = 0
                    existing_expires = self._expires(ttl)
                else:
                    if not isinstance(current, int):
                        raise TypeError(
                            f"incr() requires an int value at key {key!r}, "
                            f"got {type(current).__name__}",
                        )
                    base = current
            new_value = base + amount
            self._store[key] = (new_value, existing_expires)
            return new_value

    async def delete(self, key: str) -> None:
        """Remove ``key``. No-op if missing.

        Args:
            key: Cache key.
        """
        async with self._lock:
            self._store.pop(key, None)

    async def health_check(self) -> HealthSnapshot:
        """Probe — the memory backend is always healthy.

        Returns:
            ``HealthSnapshot(healthy=True, backend='memory')``.
        """
        return HealthSnapshot(healthy=True, backend="memory")

    def _expires(self, ttl: int | None) -> float | None:
        return None if ttl is None else self._clock.monotonic() + ttl
