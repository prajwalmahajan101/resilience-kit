"""In-process async circuit breaker — default backend, no I/O deps.

State machine (LLD §4):

  CLOSED → OPEN     on ``fail_max`` consecutive failures
  OPEN → HALF_OPEN  ``reset_timeout`` seconds after opening
  HALF_OPEN → CLOSED on ``success_threshold`` consecutive successes
  HALF_OPEN → OPEN   on any failure

Exclusions:
  * ``asyncio.CancelledError`` — never counted.
  * Classes in ``config.excluded_exceptions`` — never counted.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, TypeVar

from resilience_kit.circuit_breaker.base import (
    BreakerConfig,
    BreakerState,
    HealthSnapshot,
)
from resilience_kit.exceptions import ServiceUnavailableError
from resilience_kit.metrics import get_metrics
from resilience_kit.testing.fakes import Clock, SystemClock

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


class InMemoryAsyncBreaker:
    """In-process async breaker.

    Per-breaker state is guarded by a single ``asyncio.Lock``. The OPEN →
    HALF_OPEN transition is opportunistic — it runs inside the next
    ``call`` after the timeout elapses, no background task required.
    """

    def __init__(
        self,
        name: str,
        config: BreakerConfig | None = None,
        *,
        clock: Clock | None = None,
    ) -> None:
        """Initialise a CLOSED breaker.

        Args:
            name: Service identifier — used in metrics tags and in
                :class:`ServiceUnavailableError`.
            config: Per-breaker config; defaults to :class:`BreakerConfig`'s defaults.
            clock: Injectable clock for tests; defaults to :class:`SystemClock`.
        """
        self.name = name
        self.config = config or BreakerConfig()
        self._clock = clock or SystemClock()
        self._lock = asyncio.Lock()
        self._state = BreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float | None = None

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Invoke ``func`` through the breaker.

        Args:
            func: Coroutine function to call.
            *args: Positional arguments forwarded to ``func``.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            Whatever ``func`` returned.

        Raises:
            ServiceUnavailableError: The breaker is OPEN.
        """
        await self._maybe_half_open()
        async with self._lock:
            if self._state is BreakerState.OPEN:
                get_metrics().incr("breaker.short_circuit", tags={"service": self.name})
                raise ServiceUnavailableError(self.name)
        try:
            result = await func(*args, **kwargs)
        except asyncio.CancelledError:
            # Cancellation is not a service failure — propagate without counting.
            raise
        except self.config.excluded_exceptions:
            # Excluded exceptions propagate but do not count as breaker failures.
            raise
        except BaseException:
            await self._record_failure()
            raise
        else:
            await self._record_success()
            return result

    async def state(self) -> BreakerState:
        """Return the current state — observability only.

        Returns:
            Current :class:`BreakerState`.
        """
        await self._maybe_half_open()
        async with self._lock:
            return self._state

    async def reset(self) -> None:
        """Force the breaker back to CLOSED."""
        async with self._lock:
            self._state = BreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._opened_at = None
            get_metrics().incr("breaker.reset", tags={"service": self.name})

    async def health_check(self) -> HealthSnapshot:
        """Probe — the memory backend is always healthy.

        Returns:
            ``HealthSnapshot(healthy=True, backend='memory')``.
        """
        async with self._lock:
            return HealthSnapshot(
                healthy=True,
                backend="memory",
                detail=f"state={self._state.value}",
            )

    async def _maybe_half_open(self) -> None:
        """If we're OPEN and the timeout elapsed, transition to HALF_OPEN."""
        async with self._lock:
            if self._state is not BreakerState.OPEN or self._opened_at is None:
                return
            if self._clock.monotonic() - self._opened_at >= self.config.reset_timeout:
                self._state = BreakerState.HALF_OPEN
                self._success_count = 0
                get_metrics().incr(
                    "breaker.half_open",
                    tags={"service": self.name},
                )

    async def _record_failure(self) -> None:
        async with self._lock:
            if self._state is BreakerState.HALF_OPEN:
                # Single failure in HALF_OPEN re-opens immediately.
                self._open_locked()
                return
            self._failure_count += 1
            get_metrics().incr("breaker.failure", tags={"service": self.name})
            if self._failure_count >= self.config.fail_max:
                self._open_locked()

    async def _record_success(self) -> None:
        async with self._lock:
            get_metrics().incr("breaker.success", tags={"service": self.name})
            if self._state is BreakerState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = BreakerState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._opened_at = None
                    get_metrics().incr("breaker.close", tags={"service": self.name})
            else:
                self._failure_count = 0

    def _open_locked(self) -> None:
        """Transition to OPEN. Caller must hold ``self._lock``."""
        self._state = BreakerState.OPEN
        self._opened_at = self._clock.monotonic()
        self._success_count = 0
        self._failure_count = 0
        get_metrics().incr("breaker.open", tags={"service": self.name})
