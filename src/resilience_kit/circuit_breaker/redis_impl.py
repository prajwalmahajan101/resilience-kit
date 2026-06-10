"""Redis / Valkey async circuit breaker — atomic Lua state machine.

Reads and writes happen inside a single ``EVALSHA`` per call, so concurrent
workers see consistent state. On any ``redis.RedisError`` we **fail open**:
log once, flip ``health`` to degraded, delegate to an embedded
:class:`InMemoryAsyncBreaker`. The recovery monitor (M2 §recovery.py)
re-probes the connection and flips us back when Redis returns.

Backend gated behind the ``[redis]`` extra — importing this module without
``redis`` installed raises :class:`MissingExtraError` immediately.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any, TypeVar

try:
    from redis import exceptions as _redis_exceptions
except ImportError as exc:  # pragma: no cover - exercised in unit tests via sys.modules
    from resilience_kit.exceptions import MissingExtraError

    raise MissingExtraError(
        extra="redis",
        install_hint="resilience-kit[redis]",
    ) from exc

from resilience_kit.circuit_breaker.base import (
    BreakerConfig,
    BreakerState,
    HealthSnapshot,
)
from resilience_kit.circuit_breaker.lua_scripts import (
    BREAKER_LUA,
    BREAKER_LUA_VERSION,
)
from resilience_kit.circuit_breaker.memory_impl import InMemoryAsyncBreaker
from resilience_kit.exceptions import ServiceUnavailableError
from resilience_kit.metrics import get_metrics
from resilience_kit.testing.fakes import Clock, SystemClock

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


_logger = logging.getLogger(__name__)
T = TypeVar("T")


class RedisAsyncBreaker:
    """Async circuit breaker backed by Redis / Valkey via atomic Lua.

    Fail-open delegation: if Redis is unreachable, we transparently route
    through an embedded :class:`InMemoryAsyncBreaker` so user traffic keeps
    flowing. The :data:`health` field reflects whether we're on the primary
    or the fallback.
    """

    def __init__(
        self,
        name: str,
        config: BreakerConfig | None = None,
        *,
        redis_client: Any,
        clock: Clock | None = None,
        key_prefix: str = "cb",
    ) -> None:
        """Initialise a Redis-backed breaker.

        Args:
            name: Service identifier (also the Redis key suffix).
            config: Per-breaker config; defaults to :class:`BreakerConfig`.
            redis_client: An ``redis.asyncio.Redis`` instance. Passing it in
                lets the caller (or tests) control connection pooling.
            clock: Injectable clock — for the embedded fallback's tests.
            key_prefix: Prefix for the Redis hash key. Defaults to ``cb``.
        """
        self.name = name
        self.config = config or BreakerConfig()
        self._redis = redis_client
        self._clock = clock or SystemClock()
        self._key = f"{key_prefix}:{name}"
        self._sha: str | None = None
        self._sha_lock = asyncio.Lock()
        self._health_lock = threading.Lock()
        self._healthy = True
        self._degraded_since: float | None = None
        self._fallback = InMemoryAsyncBreaker(name=name, config=self.config, clock=self._clock)
        self._log_degraded_once = False
        # Module-level registry call lives in ``recovery.py`` — populated by
        # callers via ``register_for_recovery`` so this module doesn't have
        # to import the recovery monitor (avoids the import cycle).

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Invoke ``func`` through the breaker.

        Args:
            func: Coroutine function.
            *args: Positional args.
            **kwargs: Keyword args.

        Returns:
            Whatever ``func`` returned.

        Raises:
            ServiceUnavailableError: The breaker is OPEN.
        """
        if not self._healthy:
            # Fail-open: route through the in-memory fallback until recovery.
            return await self._fallback.call(func, *args, **kwargs)

        try:
            available, _state, _remaining = await self._eval("is_available")
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)
            return await self._fallback.call(func, *args, **kwargs)

        if not bool(available):
            get_metrics().incr("breaker.short_circuit", tags={"service": self.name})
            raise ServiceUnavailableError(self.name)

        try:
            result = await func(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except self.config.excluded_exceptions:
            raise
        except BaseException:
            await self._record("record_failure")
            raise
        else:
            await self._record("record_success")
            return result

    async def state(self) -> BreakerState:
        """Return the current breaker state.

        Returns:
            Current :class:`BreakerState`.
        """
        if not self._healthy:
            return await self._fallback.state()
        try:
            _, state_str, _ = await self._eval("is_available")
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)
            return await self._fallback.state()
        return _STATE_MAP.get(state_str, BreakerState.CLOSED)

    async def reset(self) -> None:
        """Force CLOSED via Lua; reset the fallback in lockstep."""
        try:
            await self._eval("reset")
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)
        await self._fallback.reset()
        get_metrics().incr("breaker.reset", tags={"service": self.name})

    async def health_check(self) -> HealthSnapshot:
        """Report whether we're on the primary or the fallback.

        Returns:
            Snapshot with ``backend='redis'`` (primary) or ``'memory'`` (degraded).
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
        """Probe Redis once; on success, mark healthy and return True.

        Returns:
            ``True`` if a degraded breaker transitioned back to healthy.
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
        _logger.info("RedisAsyncBreaker[%s]: recovered, leaving fallback.", self.name)
        get_metrics().incr("breaker.recovered", tags={"service": self.name})
        return True

    async def _eval(self, action: str) -> tuple[int, str, str]:
        """Execute the atomic Lua with the given action.

        Args:
            action: One of ``is_available``, ``record_success``,
                ``record_failure``, ``reset``.

        Returns:
            Tuple ``(numeric_flag, state_string, remaining_seconds_string)``.

        Raises:
            redis.exceptions.RedisError: On any Redis transport / Lua error.
        """
        async with self._sha_lock:
            if self._sha is None:
                self._sha = await self._redis.script_load(BREAKER_LUA)

        argv = [
            action,
            str(self.config.fail_max),
            str(self.config.success_threshold),
            str(self.config.reset_timeout),
            str(self._clock.now()),
        ]
        try:
            res = await self._redis.evalsha(self._sha, 1, self._key, *argv)
        except _redis_exceptions.NoScriptError:
            async with self._sha_lock:
                self._sha = await self._redis.script_load(BREAKER_LUA)
            res = await self._redis.evalsha(self._sha, 1, self._key, *argv)
        # res is a list of bytes/strings/ints depending on the driver.
        return _decode_eval(res)

    async def _record(self, action: str) -> None:
        """Record a success/failure; swallow Redis errors to avoid masking the upstream result.

        Args:
            action: ``record_success`` or ``record_failure``.
        """
        try:
            await self._eval(action)
        except _redis_exceptions.RedisError as exc:
            self._mark_degraded(exc)

    def _mark_degraded(self, exc: BaseException) -> None:
        """Flip to fallback mode on Redis failure (idempotent, lock-guarded).

        Args:
            exc: The exception that triggered the flip.
        """
        with self._health_lock:
            if self._healthy:
                self._healthy = False
                self._degraded_since = self._clock.monotonic()
            if not self._log_degraded_once:
                _logger.warning(
                    "RedisAsyncBreaker[%s] degraded; falling back to in-memory. cause=%s",
                    self.name,
                    exc,
                )
                self._log_degraded_once = True
        get_metrics().incr("breaker.degraded", tags={"service": self.name})


_STATE_MAP: dict[str, BreakerState] = {
    "closed": BreakerState.CLOSED,
    "open": BreakerState.OPEN,
    "half_open": BreakerState.HALF_OPEN,
}


def _decode_eval(res: Any) -> tuple[int, str, str]:
    """Normalise the ``EVALSHA`` return shape across redis-py versions.

    Args:
        res: Raw EVALSHA result (list of bytes / int / str).

    Returns:
        Tuple ``(flag, state, remaining)``.
    """
    if not isinstance(res, list) or len(res) < 3:
        raise RuntimeError(f"Unexpected EVALSHA result shape: {res!r}")
    flag = int(res[0])
    state = res[1].decode() if isinstance(res[1], bytes | bytearray) else str(res[1])
    remaining = res[2].decode() if isinstance(res[2], bytes | bytearray) else str(res[2])
    return flag, state, remaining


__all__ = ["BREAKER_LUA_VERSION", "RedisAsyncBreaker"]
