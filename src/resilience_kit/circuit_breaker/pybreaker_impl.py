"""Async ``AsyncBreaker`` adapter over the synchronous ``pybreaker`` library.

``pybreaker`` is sync-first; we wrap it so callers see the kit's async
protocol. ``pybreaker.CircuitBreaker.calling()`` is a context manager that
tracks success/failure through the standard contextmanager protocol — it
works inside ``async def`` as long as the ``with`` block contains the
``await``. We avoid ``call_async`` because it's a tornado-only API in
pybreaker 1.x.

``pybreaker`` is a hard dep of the kit (M0), so this module imports it
unconditionally — no :class:`MissingExtraError` guard needed.
"""

from __future__ import annotations

import asyncio
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
            with self._breaker.calling():
                outcome: Any = func(*args, **kwargs)
                if asyncio.iscoroutine(outcome):
                    outcome = await outcome
        except pybreaker.CircuitBreakerError as exc:
            # pybreaker raises CircuitBreakerError both when:
            #   (a) the breaker was already OPEN — short-circuit, and
            #   (b) this call tripped the breaker — original exception is
            #       attached to ``__context__``.
            # The kit's contract is: propagate the underlying exception
            # on the tripping call; only subsequent calls short-circuit.
            if exc.__context__ is not None:
                raise exc.__context__ from None
            get_metrics().incr("breaker.short_circuit", tags={"service": self.name})
            raise ServiceUnavailableError(self.name) from exc
        return outcome  # type: ignore[no-any-return]

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
