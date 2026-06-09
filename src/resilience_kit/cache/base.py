"""Cache protocol — TTL-aware key/value store, async-only.

Locked at v0.1 per LLD §2. Backs the JWT-blacklist, API-key debounce, and
throttle state in production. In-memory backend ships at M1; redis ships M2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from resilience_kit.circuit_breaker.base import HealthSnapshot


@runtime_checkable
class AsyncCache(Protocol):
    """Async cache protocol.

    Implementations:
        * :class:`~resilience_kit.cache.memory_impl.InMemoryAsyncCache` — ships M1.
        * ``RedisAsyncCache`` — ships M2 (extra: ``[redis]``).
    """

    async def get(self, key: str) -> Any | None:
        """Return the value at ``key``, or ``None`` if missing or expired.

        Args:
            key: Cache key.

        Returns:
            Stored value, or ``None`` if not present / expired.
        """
        ...

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set ``key`` → ``value``, optionally expiring after ``ttl`` seconds.

        Args:
            key: Cache key.
            value: Value to store.
            ttl: Time-to-live in seconds; ``None`` means no expiry.
        """
        ...

    async def add(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set ``key`` only if it does not exist (NX semantics).

        Args:
            key: Cache key.
            value: Value to store.
            ttl: Time-to-live in seconds.

        Returns:
            ``True`` if the key was created, ``False`` if it already existed.
        """
        ...

    async def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        """Atomically increment ``key`` by ``amount``, creating it at ``0`` if missing.

        Args:
            key: Cache key.
            amount: Increment delta (may be negative).
            ttl: TTL to set when the key is created; ignored if it already exists.

        Returns:
            New value after increment.
        """
        ...

    async def delete(self, key: str) -> None:
        """Remove ``key`` from the cache. No-op if missing.

        Args:
            key: Cache key.
        """
        ...

    async def health_check(self) -> HealthSnapshot:
        """Probe the backend behind this cache.

        Returns:
            Snapshot describing whether the backend is healthy.
        """
        ...
