"""Redis / Valkey async throttle — atomic Lua sliding-window check.

Per-call probe + degraded fallback mirror the breaker's pattern: on any
``RedisError`` we delegate to an embedded :class:`InMemoryAsyncThrottle`
and log once. Quiet workers don't keep PINGing — the in-call probe is
gated by :attr:`_recovery_probe_interval_seconds` (default 30 s).

Backend gated behind the ``[redis]`` extra.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

try:
    from redis import exceptions as _redis_exceptions
except ImportError as exc:  # pragma: no cover
    from resilience_kit.exceptions import MissingExtraError

    raise MissingExtraError(
        extra="redis",
        install_hint="resilience-kit[redis]",
    ) from exc

from resilience_kit.circuit_breaker.base import HealthSnapshot
from resilience_kit.metrics import get_metrics
from resilience_kit.testing.fakes import Clock, SystemClock
from resilience_kit.throttle.base import Rate, ThrottleDecision
from resilience_kit.throttle.lua_scripts import SLIDING_WINDOW_LUA
from resilience_kit.throttle.memory_impl import InMemoryAsyncThrottle

_logger = logging.getLogger(__name__)


class RedisAsyncThrottle:
    """Async throttle backed by Redis / Valkey via atomic Lua."""

    def __init__(
        self,
        *,
        redis_client: Any,
        clock: Clock | None = None,
        key_prefix: str = "throttle",
        recovery_probe_interval_seconds: float = 30.0,
    ) -> None:
        """Initialise a Redis-backed throttle.

        Args:
            redis_client: A ``redis.asyncio.Redis`` instance.
            clock: Injectable clock — for the embedded fallback.
            key_prefix: Prefix prepended to caller-supplied keys.
            recovery_probe_interval_seconds: Minimum seconds between
                in-call PINGs while degraded. Quiet workers stay quiet.
        """
        self._redis = redis_client
        self._clock = clock or SystemClock()
        self._prefix = key_prefix
        self._sha: str | None = None
        self._sha_lock = asyncio.Lock()
        self._health_lock = threading.Lock()
        self._healthy = True
        self._degraded_since: float | None = None
        self._last_probe_at = 0.0
        self._probe_interval = recovery_probe_interval_seconds
        self._fallback = InMemoryAsyncThrottle(clock=self._clock)
        self._log_degraded_once = False

    async def check(self, key: str, rate: Rate) -> ThrottleDecision:
        """Atomically admit-or-deny one event for ``key``.

        Args:
            key: Caller-derived key.
            rate: Limit to apply.

        Returns:
            Decision describing the outcome.
        """
        if not self._healthy and not await self._maybe_probe():
            return await self._fallback.check(key, rate)

        try:
            res = await self._eval(key, rate)
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)
            return await self._fallback.check(key, rate)

        allowed, count, ttl = res
        remaining = max(0, rate.count - count)
        now_int = int(self._clock.now())
        reset_at = now_int + int(ttl)
        return ThrottleDecision(
            allowed=bool(allowed),
            remaining=remaining,
            limit=rate.count,
            reset_after=float(ttl),
            reset_at=reset_at,
        )

    async def reset(self, key: str) -> None:
        """Forget any state stored for ``key``.

        Args:
            key: Key to clear.
        """
        full_key = f"{self._prefix}:{key}"
        try:
            await self._redis.delete(full_key)
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)
        await self._fallback.reset(key)

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
            detail="redis unreachable; serving via in-memory fallback",
        )

    async def try_recover(self) -> bool:
        """Probe Redis once; on success, mark healthy.

        Returns:
            ``True`` if a degraded throttle transitioned back to healthy.
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
        _logger.info("RedisAsyncThrottle: recovered, leaving fallback.")
        get_metrics().incr("throttle.recovered")
        return True

    async def _maybe_probe(self) -> bool:
        """In-call probe — at most once per ``recovery_probe_interval_seconds``.

        Returns:
            ``True`` if we successfully re-established the primary path.
        """
        now = self._clock.monotonic()
        if now - self._last_probe_at < self._probe_interval:
            return False
        self._last_probe_at = now
        return await self.try_recover()

    async def _eval(self, key: str, rate: Rate) -> tuple[int, int, int]:
        """Execute the sliding-window Lua.

        Args:
            key: Caller-derived key.
            rate: Limit to apply.

        Returns:
            ``(allowed_int, current_count, ttl_seconds)``.
        """
        full_key = f"{self._prefix}:{key}"
        async with self._sha_lock:
            if self._sha is None:
                self._sha = await self._redis.script_load(SLIDING_WINDOW_LUA)
        argv = [str(rate.count), str(int(rate.per_seconds)), str(self._clock.now())]
        try:
            res = await self._redis.evalsha(self._sha, 1, full_key, *argv)
        except _redis_exceptions.NoScriptError:
            async with self._sha_lock:
                self._sha = await self._redis.script_load(SLIDING_WINDOW_LUA)
            res = await self._redis.evalsha(self._sha, 1, full_key, *argv)
        return int(res[0]), int(res[1]), int(res[2])

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
                    "RedisAsyncThrottle degraded; falling back to in-memory. cause=%s",
                    exc,
                )
                self._log_degraded_once = True
        get_metrics().incr("throttle.degraded")
