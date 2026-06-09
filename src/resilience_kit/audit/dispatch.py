"""Audit dispatchers — fire-and-forget worker + inline (test) variant (LLD §7).

Two implementations of the :class:`AuditDispatcher` Protocol:

* :class:`FireAndForgetDispatcher` — production default. Wraps the
  shared :class:`~resilience_kit.dispatch.FireAndForget` worker with
  a sanitiser pass and a backend retry loop (x3 with backoff, then
  fall back to stdlib_logging and bump ``audit.write_failed``).
* :class:`InlineDispatcher` — synchronous-friendly test helper.
  Sanitises + writes in the calling task; surfaces backend errors so
  tests can assert on them.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from resilience_kit.audit.backends.base import (  # noqa: TC001 — runtime use (Protocol param + dataclass replace).
    AuditBackend,
    AuditEvent,
)
from resilience_kit.audit.backends.stdlib_logging import StdlibLoggingAuditBackend
from resilience_kit.audit.sanitizers import DefaultRedactor, Sanitizer
from resilience_kit.dispatch.fire_and_forget import FireAndForget, OverflowPolicy
from resilience_kit.metrics import get_metrics

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger(__name__)

# LLD §7 — three retries with exponential backoff capped at 1s.
_BACKEND_MAX_ATTEMPTS = 3
_BACKEND_BACKOFF_BASE_S = 0.05
_BACKEND_BACKOFF_CAP_S = 1.0


@runtime_checkable
class AuditDispatcher(Protocol):
    """Hand events from decorators to backends without blocking the caller."""

    def submit(self, event: AuditEvent) -> bool:
        """Enqueue an event for storage.

        Args:
            event: The audit event captured by ``@log_inbound`` /
                ``@log_outbound``.

        Returns:
            ``True`` on accept, ``False`` when dropped (e.g. overflow).
        """
        ...

    async def aclose(self, *, drain_timeout: float = 5.0) -> None:
        """Drain pending events and stop background work.

        Args:
            drain_timeout: Maximum seconds to wait for the queue to
                drain before forcing shutdown.
        """
        ...


class FireAndForgetDispatcher:
    """Production audit dispatcher per LLD §7.

    Workflow per batch:

    1. Apply :class:`Sanitizer` to every event's ``payload`` and
       ``details`` (the dispatcher owns redaction so backends never
       see raw secrets).
    2. Call :meth:`AuditBackend.write_many` with retry x3 + backoff
       on transient failure.
    3. Final retry exhausted → log batch via the fallback
       :class:`StdlibLoggingAuditBackend` and bump
       ``audit.write_failed`` with the original backend's name as a
       tag.
    """

    def __init__(
        self,
        backend: AuditBackend,
        *,
        sanitizer: Sanitizer | None = None,
        queue_size: int = 10_000,
        batch_max: int = 100,
        batch_interval_ms: int = 50,
        fallback: AuditBackend | None = None,
    ) -> None:
        """Configure the dispatcher.

        Args:
            backend: Primary audit backend (typically Postgres or stdlib
                logging). Errors trigger the retry + fallback path.
            sanitizer: Payload sanitiser. Defaults to
                :class:`DefaultRedactor`.
            queue_size: Maximum events held before overflow (drop-newest +
                ``audit.dropped``).
            batch_max: Maximum events per ``write_many`` call.
            batch_interval_ms: Maximum wait between batch flushes.
            fallback: Backend used after final retry failure. Defaults
                to :class:`StdlibLoggingAuditBackend` so audit data is
                never silently lost.
        """
        self._backend = backend
        self._sanitizer = sanitizer or DefaultRedactor()
        self._fallback = fallback or StdlibLoggingAuditBackend()
        self._backend_name = type(backend).__name__
        self._worker: FireAndForget[AuditEvent] = FireAndForget(
            self._flush,
            queue_size=queue_size,
            batch_max=batch_max,
            batch_interval_ms=batch_interval_ms,
            overflow=OverflowPolicy.DROP_NEWEST,
            metric_prefix="audit",
            name=self._backend_name,
        )

    def submit(self, event: AuditEvent) -> bool:
        """Enqueue ``event`` for asynchronous storage."""
        return self._worker.submit(event)

    async def aclose(self, *, drain_timeout: float = 5.0) -> None:
        """Drain pending events and stop the worker."""
        await self._worker.aclose(drain_timeout=drain_timeout)

    async def _flush(self, batch: Sequence[AuditEvent]) -> None:
        sanitised = [self._sanitize_event(e) for e in batch]
        await self._write_with_retry(sanitised)

    def _sanitize_event(self, event: AuditEvent) -> AuditEvent:
        return replace(
            event,
            payload=self._sanitizer.sanitize(event.payload),
            details=self._sanitizer.sanitize(event.details),
        )

    async def _write_with_retry(self, events: Sequence[AuditEvent]) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, _BACKEND_MAX_ATTEMPTS + 1):
            try:
                await self._backend.write_many(events)
            except Exception as exc:
                last_exc = exc
                if attempt < _BACKEND_MAX_ATTEMPTS:
                    await asyncio.sleep(self._backoff_s(attempt))
                continue
            return
        _logger.exception(
            "Audit backend '%s' exhausted retries; falling back to stdlib_logging.",
            self._backend_name,
            exc_info=last_exc,
        )
        get_metrics().incr(
            "audit.write_failed",
            value=len(events),
            tags={"backend": self._backend_name},
        )
        # Final attempt via the fallback backend — failure here is logged
        # but never re-raised; we have already lost the durability promise.
        try:
            await self._fallback.write_many(events)
        except Exception:
            _logger.exception("Audit fallback also failed; events lost.")

    @staticmethod
    def _backoff_s(attempt: int) -> float:
        """Exponential backoff + jitter, capped at ``_BACKEND_BACKOFF_CAP_S``."""
        base = min(
            _BACKEND_BACKOFF_BASE_S * (2 ** (attempt - 1)),
            _BACKEND_BACKOFF_CAP_S,
        )
        jitter: float = 0.5 + float(random.random())  # noqa: S311 — backoff jitter, not crypto
        return float(base * jitter)


class InlineDispatcher:
    """Synchronous-friendly dispatcher used by tests.

    Sanitises in the calling task and awaits :meth:`write_many`
    immediately. Backend failures surface so tests can assert on them.
    """

    def __init__(
        self,
        backend: AuditBackend,
        *,
        sanitizer: Sanitizer | None = None,
    ) -> None:
        """Bind the dispatcher to a backend + optional sanitiser."""
        self._backend = backend
        self._sanitizer = sanitizer or DefaultRedactor()
        self._loop_pending: list[AuditEvent] = []

    def submit(self, event: AuditEvent) -> bool:
        """Sanitise + buffer for the next :meth:`flush` call.

        Returns:
            Always ``True`` — the inline dispatcher never drops events.
        """
        sanitised = replace(
            event,
            payload=self._sanitizer.sanitize(event.payload),
            details=self._sanitizer.sanitize(event.details),
        )
        self._loop_pending.append(sanitised)
        return True

    async def flush(self) -> None:
        """Write buffered events through the backend.

        Backend failures propagate to the caller — that is the whole
        point of an inline dispatcher in tests.
        """
        if not self._loop_pending:
            return
        batch = list(self._loop_pending)
        self._loop_pending.clear()
        await self._backend.write_many(batch)

    async def aclose(self, *, drain_timeout: float = 5.0) -> None:
        """Flush remaining events; ``drain_timeout`` is accepted for parity."""
        await self.flush()


__all__ = [
    "AuditDispatcher",
    "FireAndForgetDispatcher",
    "InlineDispatcher",
]
