"""No-op audit backend — drops every event silently.

Default when ``settings.audit.sink="noop"``. Used in tests and in
deployments where audit is enabled at the decorator layer but the
storage side is owned elsewhere (e.g. an OTel collector reading the
metrics-sink stream).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from resilience_kit.audit.backends.base import AuditEvent


class NoopAuditBackend:
    """Drop every event on the floor; always healthy."""

    async def write_many(self, events: Sequence[AuditEvent]) -> None:
        """Discard the batch."""

    async def health_check(self) -> bool:
        """Always healthy — there is no storage to be unhealthy."""
        return True


__all__ = ["NoopAuditBackend"]
