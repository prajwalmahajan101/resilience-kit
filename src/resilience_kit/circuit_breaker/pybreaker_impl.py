"""Async ``AsyncBreaker`` adapter over the synchronous ``pybreaker`` library.

``pybreaker`` ships native async support via ``CircuitBreaker.call_async``
since 1.0; we delegate directly. Sync upstreams run on the thread executor
through ``CircuitBreaker.call``.

``pybreaker`` is a hard dep of the kit (M0), so this module imports it
unconditionally — no :class:`MissingExtraError` guard needed.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, TypeVar

import pybreaker

from resilience_kit.circuit_breaker.base import (
    BreakerConfig,
    BreakerState,
    HealthSnapshot,
)
from resilience_kit.exceptions import ServiceUnavailableError
from resilience_kit.metrics import get_metrics

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


T = TypeVar("T")


_PYBREAKER_STATE_MAP: dict[str, BreakerState] = {
    "closed": BreakerState.CLOSED,
    "open": BreakerState.OPEN,
    "half-open": BreakerState.HALF_OPEN,
}


class PyBreakerAsyncBreaker:
    """Async wrapper around :class:`pybreaker.CircuitBreaker`."""

    def __init__(
        self,
        name: str,
        config: BreakerConfig | None = None,
    ) -> None:
        """Initialise a fresh pybreaker-backed breaker.

        Args:
            name: Service identifier.
            config: Optional config; defaults to :class:`BreakerConfig`'s defaults.
        """
        self.name = name
        self.config = config or BreakerConfig()
        excluded = (
            *self.config.excluded_exceptions,
            # ``asyncio.CancelledError`` must never count as a breaker
            # failure — adding it to ``exclude`` makes pybreaker pass it
            # through transparently.
            asyncio.CancelledError,
        )
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=self.config.fail_max,
            reset_timeout=self.config.reset_timeout,
            exclude=list(excluded),
            name=name,
        )

    async def call(
        self,
        func: Callable[..., Awaitable[T] | T],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Invoke ``func`` through the breaker.

        Args:
            func: Sync or async callable.
            *args: Positional args.
            **kwargs: Keyword args.

        Returns:
            Whatever ``func`` returned.

        Raises:
            ServiceUnavailableError: The breaker is OPEN.
        """
        try:
            if inspect.iscoroutinefunction(func):
                result = await self._breaker.call_async(func, *args, **kwargs)  # type: ignore[no-untyped-call]
            else:
                # ``pybreaker.call`` is sync; run it on a worker thread so we
                # don't block the event loop on long-running upstreams.
                result = await asyncio.to_thread(self._breaker.call, func, *args, **kwargs)
        except pybreaker.CircuitBreakerError as exc:
            get_metrics().incr("breaker.short_circuit", tags={"service": self.name})
            raise ServiceUnavailableError(self.name) from exc
        else:
            return result  # type: ignore[no-any-return]

    async def state(self) -> BreakerState:
        """Return the current breaker state.

        Returns:
            Translated :class:`BreakerState`.
        """
        return _PYBREAKER_STATE_MAP.get(self._breaker.current_state, BreakerState.CLOSED)

    async def reset(self) -> None:
        """Force the breaker back to CLOSED."""
        self._breaker.close()
        get_metrics().incr("breaker.reset", tags={"service": self.name})

    async def health_check(self) -> HealthSnapshot:
        """Probe — the pybreaker backend is always locally healthy.

        Returns:
            ``HealthSnapshot(healthy=True, backend='pybreaker')``.
        """
        state = await self.state()
        return HealthSnapshot(
            healthy=True,
            backend="pybreaker",
            detail=f"state={state.value}",
        )
