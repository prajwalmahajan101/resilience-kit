"""Fake audit backend for the entry-point resolution test."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.circuit_breaker.base import HealthSnapshot

if TYPE_CHECKING:
    from collections.abc import Sequence


class FakeAuditBackend:
    """Trivial audit backend — collects events in memory."""

    def __init__(self, **_kwargs: Any) -> None:
        """Accept arbitrary kwargs so the provider chain can pass any."""
        self.events: list[Any] = []

    async def write(self, event: Any) -> None:
        """Record a single event."""
        await self.write_many([event])

    async def write_many(self, events: Sequence[Any]) -> None:
        """Record the batch."""
        self.events.extend(events)

    async def health_check(self) -> HealthSnapshot:
        """Always healthy."""
        return HealthSnapshot(healthy=True, backend="fake_third_party")
