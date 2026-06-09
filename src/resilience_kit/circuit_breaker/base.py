"""Circuit-breaker protocol and shared types.

Locked at v0.1 per LLD §2. Backends implement :class:`AsyncBreaker`; the
``call`` method is the only public method callers invoke directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


T = TypeVar("T")


class BreakerState(StrEnum):
    """State of the circuit breaker.

    Transitions:
        CLOSED → OPEN     on ``fail_max`` consecutive failures
        OPEN → HALF_OPEN  after ``reset_timeout`` seconds
        HALF_OPEN → CLOSED on ``success_threshold`` consecutive successes
        HALF_OPEN → OPEN   on any failure
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class BreakerConfig:
    """Per-breaker configuration.

    Defaults follow LLD §10 / settings ``defaults.circuit_breaker``.
    """

    fail_max: int = 5
    reset_timeout: float = 30.0
    success_threshold: int = 2
    excluded_exceptions: tuple[type[BaseException], ...] = ()


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    """Backend health probe result — used by the recovery monitor and ``/readyz``."""

    healthy: bool
    backend: str
    degraded_since: float | None = None
    detail: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AsyncBreaker(Protocol):
    """Async circuit-breaker protocol.

    Concrete implementations:
        * :class:`~resilience_kit.circuit_breaker.memory_impl.InMemoryAsyncBreaker` — ships M1.
        * ``PyBreakerAsyncBreaker`` — ships M2 (extra: ``[pybreaker]``).
        * ``RedisAsyncBreaker``     — ships M2 (extra: ``[redis]``).
    """

    name: str
    config: BreakerConfig

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
        ...

    async def state(self) -> BreakerState:
        """Return the current state — observability only.

        Returns:
            Current :class:`BreakerState`.
        """
        ...

    async def reset(self) -> None:
        """Force the breaker back to CLOSED. Mgmt / test hook."""
        ...

    async def health_check(self) -> HealthSnapshot:
        """Probe the backend behind this breaker.

        Returns:
            Snapshot describing whether the backend is healthy and, if not,
            when it began to degrade.
        """
        ...
