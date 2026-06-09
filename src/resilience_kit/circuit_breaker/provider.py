"""Circuit-breaker backend provider.

M1 ships only the in-memory backend; the full provider chain (explicit →
settings → entry-point → builtin) lands in M2 once Redis + pybreaker
backends exist. The function signature is locked now so callers don't need
to migrate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resilience_kit.circuit_breaker.memory_impl import InMemoryAsyncBreaker

if TYPE_CHECKING:
    from resilience_kit.circuit_breaker.base import AsyncBreaker, BreakerConfig
    from resilience_kit.testing.fakes import Clock


def get_breaker(
    *,
    name: str,
    config: BreakerConfig,
    clock: Clock | None = None,
) -> AsyncBreaker:
    """Return a breaker instance for ``name``.

    At M1 always returns an :class:`InMemoryAsyncBreaker`. M2 introduces
    ``resolve_provider`` for entry-point lookup of redis / pybreaker backends.

    Args:
        name: Service identifier.
        config: Per-breaker config.
        clock: Injectable clock — for tests.

    Returns:
        A breaker instance.
    """
    return InMemoryAsyncBreaker(name=name, config=config, clock=clock)
