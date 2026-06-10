"""FastAPI exception handlers for the kit exception hierarchy.

Plain FastAPI lets exceptions bubble to a default 500-with-traceback
handler. The adapter installs handlers that translate every
:class:`~resilience_kit.exceptions.ResilienceKitError` into the locked
LLD §11 JSON envelope::

    {"error_code": str, "message": str, "details": dict}

with the HTTP status from
:func:`~resilience_kit.exceptions.http_status_for` and, for
:class:`~resilience_kit.exceptions.RateLimitError`, the standard
``Retry-After`` + ``X-RateLimit-*`` headers from
:meth:`RateLimitError.response_headers`.

The :class:`~resilience_kit.middleware.exception_logging.ExceptionLoggingMiddleware`
ASGI layer applies the same mapping for raw ASGI hosts; installing the
adapter handlers in addition gives FastAPI users richer integration
(handlers can be inspected via ``app.exception_handlers``, can be
overridden per exception, and run inside FastAPI's request lifecycle so
``request.state`` is still readable).

.. warning::

   If your app already installs its own exception handlers against a
   different envelope shape (e.g. a ``{success, message, data, errors,
   request_id}`` envelope mounted on a custom ``BaseError`` tree), do
   **not** call :func:`install` blindly — the kit handlers target
   :class:`~resilience_kit.exceptions.ResilienceKitError` and emit the
   LLD §11 envelope, which is incompatible with that shape. The M7
   FastAPI dogfooding report (§0.2) hit this: rate-limited 429s started
   returning the kit envelope while everything else returned the
   project envelope, breaking clients that pattern-matched on
   ``success: false``. The choices, in order of least friction:

   1. Subclass each kit exception into your domain hierarchy and route
      everything through your handler (apply the "exception bridge"
      pattern from ``docs/MIGRATION-from-boilerplate-embedded.md``
      §10.1).
   2. Install a thin :class:`ResilienceKitError`-catching handler
      before both handler sets that re-wraps into your envelope (see
      ``docs/MIGRATION-from-boilerplate-embedded.md`` §10.2 — a
      :func:`from_exception` helper is on the v0.1.x patch line).
   3. Accept the kit envelope as the new contract and document the
      shape change (breaking for existing clients).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from resilience_kit.adapters._envelope import from_exception
from resilience_kit.context import request_id
from resilience_kit.exceptions import (
    MissingExtraError,
    RateLimitError,
    ResilienceKitError,
    ValidationError,
)

try:
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("fastapi", "resilience-kit[fastapi]") from exc

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

_logger = logging.getLogger("resilience_kit.adapters.fastapi")


def install(app: FastAPI) -> None:
    """Register kit-aware exception handlers on ``app``.

    Installs a single handler for :class:`ResilienceKitError` (which
    covers every kit exception via subclassing) and a more specific
    one for :class:`RateLimitError` so the rate-limit response carries
    the right headers without an extra ``isinstance`` branch in the
    generic handler.

    Args:
        app: Target FastAPI application.
    """

    @app.exception_handler(RateLimitError)
    async def _on_rate_limit(_request: Request, exc: RateLimitError) -> JSONResponse:
        return _envelope(exc)

    @app.exception_handler(ResilienceKitError)
    async def _on_kit_error(_request: Request, exc: ResilienceKitError) -> JSONResponse:
        return _envelope(exc)


def _envelope(exc: ResilienceKitError) -> JSONResponse:
    """Build the LLD §11 JSON response for ``exc``."""
    is_warning = isinstance(exc, (ValidationError, RateLimitError))
    severity = logging.WARNING if is_warning else logging.ERROR
    _logger.log(
        severity,
        "%s: %s",
        exc.error_code,
        exc,
        extra={
            "error_code": exc.error_code,
            "details": dict(exc.details),
            "request_id": request_id.get(),
        },
    )
    body, status, headers = from_exception(exc)
    return JSONResponse(body, status_code=status, headers=headers)


__all__ = ["install"]
