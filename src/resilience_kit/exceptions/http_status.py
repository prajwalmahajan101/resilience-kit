"""LLD §11 exception → HTTP-status mapping.

The table is locked at v0.1. ASGI middleware
(:class:`~resilience_kit.middleware.exception_logging.ExceptionLoggingMiddleware`)
and the framework adapters (FastAPI exception handlers in M5, DRF
exception handler in M6) all derive the response status from
:func:`http_status_for` so a single source of truth governs the
HTTP contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resilience_kit.exceptions.infrastructure import (
    DecryptionError,
    ExternalServiceError,
    ExternalTimeoutError,
    RepositoryError,
    ServiceUnavailableError,
)
from resilience_kit.exceptions.validation import RateLimitError, ValidationError

if TYPE_CHECKING:
    from resilience_kit.exceptions.base import ResilienceKitError

#: LLD §11 — locked at v0.1. Order matters: most specific class first so
#: ``isinstance()`` resolution lands on the narrower mapping when
#: subclasses overlap (e.g. :class:`ExternalTimeoutError` is also a
#: :class:`TransientError`).
HTTP_STATUS_MAP: tuple[tuple[type[ResilienceKitError], int], ...] = (
    (ValidationError, 400),
    (RateLimitError, 429),
    (ServiceUnavailableError, 503),
    (ExternalTimeoutError, 504),
    (ExternalServiceError, 502),
    (DecryptionError, 500),
    (RepositoryError, 500),
)


def http_status_for(exc: ResilienceKitError) -> int:
    """Return the LLD §11 HTTP status for ``exc``.

    Args:
        exc: Any kit exception (or subclass).

    Returns:
        ``400`` / ``429`` / ``500`` / ``502`` / ``503`` / ``504`` per
        :data:`HTTP_STATUS_MAP`. Falls back to ``500`` for
        :class:`ResilienceKitError` subclasses not yet on the table.
    """
    for cls, status in HTTP_STATUS_MAP:
        if isinstance(exc, cls):
            return status
    return 500


__all__ = ["HTTP_STATUS_MAP", "http_status_for"]
