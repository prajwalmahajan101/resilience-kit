"""Audit backend that logs events through :mod:`logging`.

The default ``settings.audit.sink="stdlib_logging"`` ships every event
as a structured log record at INFO level — fine for development, useful
in production deployments that have a centralised log shipper.

Each :class:`~resilience_kit.audit.AuditEvent` becomes a log record with
``extra=event.__dict__`` so downstream processors (``json`` formatter,
``logfmt`` filter, etc.) can pick up the structured fields without
reparsing the message.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import TYPE_CHECKING

from resilience_kit.circuit_breaker.base import HealthSnapshot

if TYPE_CHECKING:
    from collections.abc import Sequence

    from resilience_kit.audit.backends.base import AuditEvent

_logger = logging.getLogger("resilience_kit.audit")


class StdlibLoggingAuditBackend:
    """Emit each audit event as a structured ``INFO`` log record."""

    def __init__(self, *, logger_name: str = "resilience_kit.audit") -> None:
        """Bind the backend to a named logger.

        Args:
            logger_name: Logger to emit records on. Useful when callers
                want per-service routing via ``logging`` filters.
        """
        self._logger = logging.getLogger(logger_name)

    async def write(self, event: AuditEvent) -> None:
        """Emit a single event (delegates to :meth:`write_many`)."""
        await self.write_many([event])

    async def write_many(self, events: Sequence[AuditEvent]) -> None:
        """Emit one INFO record per event with the event fields in ``extra``."""
        for event in events:
            self._logger.info(
                "audit %s %s %s %s status=%s outcome=%s latency_ms=%.2f",
                event.direction,
                event.service,
                event.method,
                event.path,
                event.status,
                event.outcome,
                event.latency_ms,
                extra={"audit_event": asdict(event)},
            )

    async def health_check(self) -> HealthSnapshot:
        """Always healthy — logging cannot fail this aggregator."""
        return HealthSnapshot(healthy=True, backend="stdlib_logging")


__all__ = ["StdlibLoggingAuditBackend"]
