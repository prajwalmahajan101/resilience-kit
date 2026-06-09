"""Circuit breaker subpackage — protocol, state, and backends.

Public surface: :class:`AsyncBreaker`, :class:`BreakerState`,
:class:`BreakerConfig`, :class:`HealthSnapshot`. In-memory backend ships at
M1; redis + pybreaker backends ship at M2.
"""

from __future__ import annotations

from resilience_kit.circuit_breaker.base import (
    AsyncBreaker,
    BreakerConfig,
    BreakerState,
    HealthSnapshot,
)

__all__ = ["AsyncBreaker", "BreakerConfig", "BreakerState", "HealthSnapshot"]
