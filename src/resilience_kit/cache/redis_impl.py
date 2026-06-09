"""Redis / Valkey async TTL cache.

Pure stdlib Redis ops — no custom Lua. On any ``RedisError`` we fall back
to an embedded :class:`InMemoryAsyncCache` for every operation *except*
:meth:`incr`, which raises :class:`KeyError` rather than diverge on the
authoritative counter (the boilerplate's behaviour — fail-open on read
paths, fail-loud on write-once-only ones).

Backend gated behind the ``[redis]`` extra.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

try:
    from redis import exceptions as _redis_exceptions
except ImportError as exc:  # pragma: no cover
    from resilience_kit.exceptions import MissingExtraError

    raise MissingExtraError(
        extra="redis",
        install_hint="prajwal-resilience-kit[redis]",
    ) from exc

from resilience_kit.cache.memory_impl import InMemoryAsyncCache
from resilience_kit.circuit_breaker.base import HealthSnapshot
from resilience_kit.metrics import get_metrics
from resilience_kit.testing.fakes import Clock, SystemClock

_logger = logging.getLogger(__name__)


class RedisAsyncCache:
    """Async cache backed by Redis / Valkey.

    Values are stored as bytes — callers serialize before ``set`` and
    deserialize after ``get``. The kit doesn't impose a serialization
    format (callers commonly use ``json.dumps`` or ``msgpack``).
    """

    def __init__(
        self,
        *,
        redis_client: Any,
        alias: str = "default",
        clock: Clock | None = None,
        key_prefix: str = "",
        recovery_probe_interval_seconds: float = 30.0,
    ) -> None:
        """Initialise a Redis-backed cache.

        Args:
            redis_client: A ``redis.asyncio.Redis`` instance.
            alias: Logical name for this cache (multi-cache deployments).
            clock: Injectable clock — for the embedded fallback.
            key_prefix: Prefix prepended to caller-supplied keys.
            recovery_probe_interval_seconds: Min seconds between in-call PINGs.
        """
        self._redis = redis_client
        self._alias = alias
        self._clock = clock or SystemClock()
        self._prefix = key_prefix
        self._health_lock = threading.Lock()
        self._healthy = True
        self._degraded_since: float | None = None
        self._last_probe_at = 0.0
        self._probe_interval = recovery_probe_interval_seconds
        self._fallback = InMemoryAsyncCache(clock=self._clock)
        self._log_degraded_once = False

    async def get(self, key: str) -> Any | None:
        """Return the value at ``key`` or ``None`` if missing.

        Args:
            key: Cache key.

        Returns:
            Stored value (bytes) or ``None``.
        """
        if not self._healthy and not await self._maybe_probe():
            return await self._fallback.get(key)
        try:
            return await self._redis.get(self._k(key))
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)
            return await self._fallback.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set ``key`` → ``value``, optionally expiring after ``ttl`` seconds.

        Args:
            key: Cache key.
            value: Bytes (or anything redis-py will encode).
            ttl: Time-to-live in seconds.
        """
        if not self._healthy and not await self._maybe_probe():
            await self._fallback.set(key, value, ttl)
            return
        try:
            await self._redis.set(self._k(key), value, ex=ttl)
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)
            await self._fallback.set(key, value, ttl)

    async def add(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """NX-set ``key`` → ``value``. Returns ``True`` only if created.

        Args:
            key: Cache key.
            value: Bytes (or redis-py-encodable).
            ttl: Time-to-live in seconds.

        Returns:
            ``True`` if the key was created.
        """
        if not self._healthy and not await self._maybe_probe():
            return await self._fallback.add(key, value, ttl)
        try:
            res = await self._redis.set(self._k(key), value, ex=ttl, nx=True)
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)
            return await self._fallback.add(key, value, ttl)
        return bool(res)

    async def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        """Atomically increment ``key`` by ``amount``.

        ``incr`` is the one operation where we **do not** fall back: an
        authoritative counter that silently diverges across workers is
        worse than a loud error. Callers wrap their counter logic with
        the breaker if they need resilience.

        Args:
            key: Cache key.
            amount: Increment delta (may be negative).
            ttl: TTL to set when the key is first created.

        Returns:
            New value after increment.

        Raises:
            redis.exceptions.RedisError: Re-raised when Redis is unreachable.
        """
        full = self._k(key)
        if amount >= 0:
            new_value = int(await self._redis.incrby(full, amount))
        else:
            new_value = int(await self._redis.decrby(full, -amount))
        if ttl is not None and new_value == amount:
            # Just created — set the TTL.
            await self._redis.expire(full, ttl)
        return new_value

    async def delete(self, key: str) -> None:
        """Remove ``key``. No-op if missing.

        Args:
            key: Cache key.
        """
        if not self._healthy and not await self._maybe_probe():
            await self._fallback.delete(key)
            return
        try:
            await self._redis.delete(self._k(key))
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)
            await self._fallback.delete(key)

    async def health_check(self) -> HealthSnapshot:
        """Probe Redis once and report.

        Returns:
            Snapshot with ``backend='redis'`` or ``'memory'``.
        """
        if self._healthy:
            try:
                await self._redis.ping()
            except _redis_exceptions.RedisError as exc:
                self._mark_degraded(exc)
            else:
                return HealthSnapshot(healthy=True, backend="redis")
        return HealthSnapshot(
            healthy=False,
            backend="memory",
            degraded_since=self._degraded_since,
            detail=f"redis unreachable; alias={self._alias}",
        )

    async def try_recover(self) -> bool:
        """Probe Redis once; on success, mark healthy.

        Returns:
            ``True`` if a degraded cache transitioned back to healthy.
        """
        if self._healthy:
            return False
        try:
            await self._redis.ping()
        except _redis_exceptions.RedisError:
            return False
        with self._health_lock:
            self._healthy = True
            self._degraded_since = None
            self._log_degraded_once = False
        _logger.info("RedisAsyncCache[%s]: recovered, leaving fallback.", self._alias)
        get_metrics().incr("cache.recovered", tags={"alias": self._alias})
        return True

    async def _maybe_probe(self) -> bool:
        """In-call probe — gated by ``recovery_probe_interval_seconds``.

        Returns:
            ``True`` if we re-established the primary path.
        """
        now = self._clock.monotonic()
        if now - self._last_probe_at < self._probe_interval:
            return False
        self._last_probe_at = now
        return await self.try_recover()

    def _k(self, key: str) -> str:
        """Return the prefixed key."""
        return f"{self._prefix}{key}" if self._prefix else key

    def _mark_degraded(self, exc: BaseException) -> None:
        """Flip to fallback (idempotent, lock-guarded).

        Args:
            exc: Triggering exception.
        """
        with self._health_lock:
            if self._healthy:
                self._healthy = False
                self._degraded_since = self._clock.monotonic()
            if not self._log_degraded_once:
                _logger.warning(
                    "RedisAsyncCache[%s] degraded; falling back to in-memory. cause=%s",
                    self._alias,
                    exc,
                )
                self._log_degraded_once = True
        get_metrics().incr("cache.degraded", tags={"alias": self._alias})
