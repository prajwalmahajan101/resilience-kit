"""Throttle protocol, rate parser, and decision dataclass.

Locked at v0.1 per LLD §2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from resilience_kit.exceptions import ValidationError

if TYPE_CHECKING:
    from resilience_kit.circuit_breaker.base import HealthSnapshot


#: Behaviour of a distributed throttle when its Redis backend is unreachable.
#:
#: ``"open"`` (default) degrades to a per-pod in-memory window — ergonomic, but
#: a global ``N/min`` limit effectively becomes ``N/min`` *per pod* during the
#: outage (an 8-pod fleet allows 8x the intended rate). ``"closed"`` denies
#: every request while degraded — correct for hard upstream limits (payment
#: APIs) at the cost of dropping traffic during a Redis outage. See ADR-0013.
ThrottleFailMode = Literal["open", "closed"]


_RATE_RE = re.compile(r"^\s*(\d+)\s*/\s*([a-z]+)\s*$", re.IGNORECASE)
_UNIT_SECONDS: dict[str, float] = {
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "m": 60.0,
    "min": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
    "days": 86400.0,
}


@dataclass(frozen=True, slots=True)
class Rate:
    """Token-bucket rate — ``count`` events per ``per_seconds`` seconds."""

    count: int
    per_seconds: float

    @classmethod
    def parse(cls, spec: str) -> Rate:
        """Parse a rate spec string like ``"60/min"``.

        Accepted units (case-insensitive): ``s/sec/second/seconds``,
        ``m/min/minute/minutes``, ``h/hr/hour/hours``, ``d/day/days``.

        Args:
            spec: Rate string.

        Returns:
            Parsed :class:`Rate`.

        Raises:
            ValidationError: ``spec`` is malformed or the unit is unknown.
        """
        m = _RATE_RE.match(spec)
        if not m:
            raise ValidationError(
                f"Malformed rate spec: {spec!r}. Expected '<count>/<unit>' (e.g. '60/min').",
                details={"spec": spec},
            )
        count = int(m.group(1))
        unit = m.group(2).lower()
        if unit not in _UNIT_SECONDS:
            raise ValidationError(
                f"Unknown rate unit {unit!r} in spec {spec!r}.",
                details={"spec": spec, "unit": unit, "known": sorted(_UNIT_SECONDS)},
            )
        if count <= 0:
            raise ValidationError(
                f"Rate count must be > 0 (got {count}).",
                details={"spec": spec, "count": count},
            )
        return cls(count=count, per_seconds=_UNIT_SECONDS[unit])


def parse_rate(spec: str) -> Rate:
    """Convenience wrapper for :meth:`Rate.parse`.

    Args:
        spec: Rate string.

    Returns:
        Parsed :class:`Rate`.
    """
    return Rate.parse(spec)


@dataclass(frozen=True, slots=True)
class ThrottleDecision:
    """Result of a throttle check.

    ``reset_after`` is seconds until the next slot opens; ``reset_at`` is the
    same instant in unix-epoch seconds (adapters use it for the
    ``X-RateLimit-Reset`` header).
    """

    allowed: bool
    remaining: int
    limit: int
    reset_after: float
    reset_at: int


@runtime_checkable
class AsyncThrottle(Protocol):
    """Async throttle protocol — token bucket / sliding window."""

    async def check(self, key: str, rate: Rate) -> ThrottleDecision:
        """Atomically count one event under ``key`` against ``rate``.

        Args:
            key: Caller-derived key (see :func:`resilience_kit.throttle.build_key`).
            rate: Limit to apply.

        Returns:
            Decision including whether the call is allowed and remaining capacity.
        """
        ...

    async def reset(self, key: str) -> None:
        """Forget any state stored for ``key``. Mgmt / test hook.

        Args:
            key: Key to clear.
        """
        ...

    async def health_check(self) -> HealthSnapshot:
        """Probe the throttle's backend.

        Returns:
            Snapshot describing backend health.
        """
        ...


__all__ = ["AsyncThrottle", "Rate", "ThrottleDecision", "ThrottleFailMode", "parse_rate"]
