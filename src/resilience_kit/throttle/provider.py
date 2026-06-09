"""Throttle backend provider — M1 returns the in-memory backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from resilience_kit.throttle.memory_impl import InMemoryAsyncThrottle

if TYPE_CHECKING:
    from resilience_kit.testing.fakes import Clock
    from resilience_kit.throttle.base import AsyncThrottle


_default: AsyncThrottle | None = None


def get_throttle(*, clock: Clock | None = None) -> AsyncThrottle:
    """Return the process-wide throttle.

    At M1 always returns the in-memory backend (cached as a singleton). M2
    introduces provider-chain resolution; tests can swap via
    :func:`reset_throttle`.

    Args:
        clock: Injectable clock — only used the first time the singleton is built.

    Returns:
        The throttle singleton.
    """
    global _default  # noqa: PLW0603 — module-level cache is the API
    if _default is None:
        _default = InMemoryAsyncThrottle(clock=clock)
    return _default


def reset_throttle() -> None:
    """Drop the cached throttle. Test hook."""
    global _default  # noqa: PLW0603 — module-level cache is the API
    _default = None
