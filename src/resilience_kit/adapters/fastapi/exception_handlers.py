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
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from resilience_kit.context import request_id
from resilience_kit.exceptions import (
    MissingExtraError,
    RateLimitError,
    ResilienceKitError,
    ValidationError,
    http_status_for,
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
        return _envelope(exc, headers=exc.response_headers())

    @app.exception_handler(ResilienceKitError)
    async def _on_kit_error(_request: Request, exc: ResilienceKitError) -> JSONResponse:
        return _envelope(exc)


def _envelope(
    exc: ResilienceKitError,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the LLD §11 JSON response for ``exc``."""
    status = http_status_for(exc)
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
    return JSONResponse(
        {
            "error_code": exc.error_code,
            "message": str(exc),
            "details": dict(exc.details),
        },
        status_code=status,
        headers=headers,
    )


__all__ = ["install"]
