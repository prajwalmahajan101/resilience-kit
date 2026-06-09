"""Clock protocol + fakes used by the contract suite.

Every primitive that reads time takes a :class:`Clock` so tests can advance
time deterministically without ``time.sleep``.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping


@runtime_checkable
class Clock(Protocol):
    """Time source — wall + monotonic + async sleep."""

    def now(self) -> float:
        """Return unix-epoch seconds (wall clock).

        Returns:
            Unix timestamp.
        """
        ...

    def monotonic(self) -> float:
        """Return a monotonic timestamp in seconds.

        Returns:
            Monotonic seconds.
        """
        ...

    async def sleep(self, seconds: float) -> None:
        """Sleep for ``seconds`` seconds.

        Args:
            seconds: Duration; negative or zero is a no-op.
        """
        ...


class SystemClock:
    """Real-world clock backed by :mod:`time` and :func:`asyncio.sleep`."""

    def now(self) -> float:
        """Return :func:`time.time`."""
        return time.time()

    def monotonic(self) -> float:
        """Return :func:`time.monotonic`."""
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        """Await :func:`asyncio.sleep`."""
        if seconds > 0:
            await asyncio.sleep(seconds)


class FakeClock:
    """Test clock — ``tick(s)`` advances both wall and monotonic time.

    ``sleep(s)`` does not actually sleep; it advances the clock and yields
    control once. Use ``await clock.sleep(s)`` to model elapsed time inside
    primitives under test.
    """

    def __init__(self, start: float = 1_700_000_000.0) -> None:
        """Initialise at the given wall time (monotonic starts at 0).

        Args:
            start: Initial wall-clock value.
        """
        self._wall = start
        self._mono = 0.0

    def now(self) -> float:
        """Return the current wall time."""
        return self._wall

    def monotonic(self) -> float:
        """Return the current monotonic time."""
        return self._mono

    async def sleep(self, seconds: float) -> None:
        """Advance the clock by ``seconds`` and yield once.

        Args:
            seconds: Duration to advance.
        """
        if seconds > 0:
            self.tick(seconds)
        # Yield so other tasks can observe the elapsed time.
        await asyncio.sleep(0)

    def tick(self, seconds: float) -> None:
        """Advance both wall and monotonic clocks by ``seconds``.

        Args:
            seconds: Duration to advance.
        """
        self._wall += seconds
        self._mono += seconds


class FakeAuditSink:
    """Collect audit events in memory — used by tests once M4 ships audit.

    Included at M1 so the test-helper public surface is locked from day one.
    """

    def __init__(self) -> None:
        """Initialise with an empty event buffer."""
        self.events: list[Mapping[str, Any]] = []

    async def write(self, event: Mapping[str, Any]) -> None:
        """Append ``event`` to the in-memory buffer.

        Args:
            event: Structured event payload.
        """
        self.events.append(event)

    def clear(self) -> None:
        """Drop all collected events."""
        self.events.clear()
