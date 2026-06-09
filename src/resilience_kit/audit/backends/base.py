"""Audit protocol + event shape (LLD §7).

:class:`AuditEvent` is the audit-shaped record produced by every
``@log_inbound`` / ``@log_outbound`` call and handed to the dispatcher.
:class:`AuditBackend` is the storage protocol the dispatcher writes to
in batches.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


Direction = Literal["inbound", "outbound"]
Outcome = Literal["success", "failure"]


@dataclass(slots=True)
class AuditEvent:
    """One audit record — request or response, inbound or outbound.

    The dataclass is the canonical wire shape; backends serialize it
    however storage requires (JSON for Postgres ``jsonb``, log message
    for stdlib_logging, etc.).
    """

    direction: Direction
    service: str
    method: str
    path: str
    outcome: Outcome
    latency_ms: float
    status: int | None = None
    error_code: str | None = None
    error_class: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    details: Mapping[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@runtime_checkable
class AuditBackend(Protocol):
    """Storage protocol for the audit subsystem.

    The dispatcher batches up to ``audit.batch_max`` events and calls
    :meth:`write_many`; backends are free to flush the batch atomically
    (Postgres ``COPY``) or individually (stdlib logging). Errors raised
    here are retried by the dispatcher per LLD §7.
    """

    async def write_many(self, events: Sequence[AuditEvent]) -> None:
        """Persist a batch of audit events.

        Args:
            events: Batch of events to write. Always non-empty.

        Raises:
            Exception: Any persistence failure. The dispatcher catches +
                retries; final failure falls back to ``stdlib_logging``
                and bumps ``audit.write_failed``.
        """
        ...

    async def health_check(self) -> bool:
        """Return ``True`` when the backend is currently usable.

        Used by the ``/readyz`` aggregator (M4 commit 2). Backends that
        are always available (``noop`` / ``stdlib_logging``) return
        ``True`` unconditionally.
        """
        ...


__all__ = ["AuditBackend", "AuditEvent", "Direction", "Outcome"]
