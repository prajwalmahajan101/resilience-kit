"""In-process async throttle — sliding window via ``deque[float]``.

For each key we keep a ``deque`` of admission timestamps; on each
:meth:`check` we drop entries older than ``rate.per_seconds``, then count
what remains. Below the limit → admit + append. At or above → deny with a
``retry_after`` derived from the oldest remaining timestamp.

Wall-clock timestamps (``clock.now()``) intentionally — matches the Redis
backend semantics shipping in M2.
"""

from __future__ import annotations

import asyncio
from collections import deque

from resilience_kit.circuit_breaker.base import HealthSnapshot
from resilience_kit.testing.fakes import Clock, SystemClock
from resilience_kit.throttle.base import Rate, ThrottleDecision


class InMemoryAsyncThrottle:
    """In-process async throttle.

    All state lives under one ``asyncio.Lock``. The throttle is per-process
    — for multi-worker production deployments, use the Redis backend (M2).
    """

    def __init__(self, clock: Clock | None = None) -> None:
        """Initialise an empty throttle.

        Args:
            clock: Injectable clock — for tests.
        """
        self._clock: Clock = clock or SystemClock()
        self._lock = asyncio.Lock()
        self._windows: dict[str, deque[float]] = {}

    async def check(self, key: str, rate: Rate) -> ThrottleDecision:
        """Atomically admit-or-deny one event for ``key``.

        Args:
            key: Caller-derived key (see :func:`~resilience_kit.throttle.build_key`).
            rate: Limit to apply.

        Returns:
            Decision describing the outcome.
        """
        now = self._clock.now()
        async with self._lock:
            window = self._windows.setdefault(key, deque())
            cutoff = now - rate.per_seconds
            while window and window[0] < cutoff:
                window.popleft()
            current = len(window)
            allowed = current < rate.count
            if allowed:
                window.append(now)
                remaining = rate.count - current - 1
                # Reset time is when the *first* admission in this window expires;
                # if the window is empty after appending, the freshly added entry.
                oldest = window[0]
                reset_at = int(oldest + rate.per_seconds)
                reset_after = max(0.0, (oldest + rate.per_seconds) - now)
            else:
                remaining = 0
                # The oldest entry's expiry is when the next slot opens.
                oldest = window[0] if window else now
                reset_at = int(oldest + rate.per_seconds)
                reset_after = max(0.0, (oldest + rate.per_seconds) - now)
            return ThrottleDecision(
                allowed=allowed,
                remaining=remaining,
                limit=rate.count,
                reset_after=reset_after,
                reset_at=reset_at,
            )

    async def reset(self, key: str) -> None:
        """Forget any state stored for ``key``.

        Args:
            key: Key to clear.
        """
        async with self._lock:
            self._windows.pop(key, None)

    async def health_check(self) -> HealthSnapshot:
        """Probe — the memory backend is always healthy.

        Returns:
            ``HealthSnapshot(healthy=True, backend='memory')``.
        """
        return HealthSnapshot(healthy=True, backend="memory")
