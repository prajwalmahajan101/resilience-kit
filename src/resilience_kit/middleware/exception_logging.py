"""ASGI middleware mapping every kit exception onto the LLD §11 envelope.

When the inner app raises a :class:`ResilienceKitError`, the middleware:

1. Logs a structured record at the appropriate severity (WARNING for
   :class:`ValidationError` / :class:`RateLimitError`, ERROR otherwise)
   carrying ``error_code``, ``details``, and ``request_id`` from the
   ContextVar.
2. Maps the exception onto the locked LLD §11 HTTP status + JSON
   envelope::

       {"error_code": str, "message": str, "details": dict}

3. Forwards any non-kit ``Exception`` as a 500 with a generic envelope
   — the exception is logged but the stack trace never reaches the
   client.

The mapping is the same table FastAPI / Django adapters apply at the
framework layer (M5 / M6); having it in the kit's ASGI middleware means
plain ASGI hosts (raw Hypercorn, Uvicorn) get correct behaviour without
adapter glue.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from resilience_kit.context import request_id
from resilience_kit.exceptions import (
    RateLimitError,
    ResilienceKitError,
    ValidationError,
    http_status_for,
)

if TYPE_CHECKING:
    from resilience_kit.middleware._asgi import App, Receive, Scope, Send

_logger = logging.getLogger("resilience_kit.exception_logging")


class ExceptionLoggingMiddleware:
    """Convert kit exceptions into the LLD §11 JSON envelope."""

    def __init__(self, app: App) -> None:
        """Wrap ``app``."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run ``app``; intercept :class:`ResilienceKitError` and other raises."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        try:
            await self._app(scope, receive, send)
        except ResilienceKitError as exc:
            await _respond_kit_error(exc, send)
        except Exception:
            _logger.exception(
                "Unhandled exception in inner app",
                extra={"request_id": request_id.get()},
            )
            await _respond_generic_500(send)


def _severity_for(exc: ResilienceKitError) -> int:
    if isinstance(exc, (ValidationError, RateLimitError)):
        return logging.WARNING
    return logging.ERROR


async def _respond_kit_error(exc: ResilienceKitError, send: Send) -> None:
    status = http_status_for(exc)
    _logger.log(
        _severity_for(exc),
        "%s: %s",
        exc.error_code,
        exc,
        extra={
            "error_code": exc.error_code,
            "details": dict(exc.details),
            "request_id": request_id.get(),
        },
    )
    body = json.dumps(
        {
            "error_code": exc.error_code,
            "message": str(exc),
            "details": dict(exc.details),
        },
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        },
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def _respond_generic_500(send: Send) -> None:
    body = json.dumps(
        {
            "error_code": "INTERNAL_ERROR",
            "message": "Internal server error.",
            "details": {},
        },
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [(b"content-type", b"application/json")],
        },
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


__all__ = ["ExceptionLoggingMiddleware"]
