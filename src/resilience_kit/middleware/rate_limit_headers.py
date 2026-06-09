"""ASGI middleware mapping :class:`RateLimitError` onto a 429 response.

The kit's throttle decorators raise
:class:`~resilience_kit.exceptions.RateLimitError` with all the fields
the standard ``X-RateLimit-*`` headers need (limit / remaining /
reset_at / retry_after).
:meth:`RateLimitError.response_headers` returns the four-header dict
ready to splat into a response.

This middleware catches the exception from the inner app and emits the
canonical 429 + headers so the throttle's decision is uniformly
surfaced regardless of which view raised.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from resilience_kit.exceptions import RateLimitError

if TYPE_CHECKING:
    from resilience_kit.middleware._asgi import App, Receive, Scope, Send


class RateLimitHeadersMiddleware:
    """Catch :class:`RateLimitError` and respond with 429 + ``X-RateLimit-*``."""

    def __init__(self, app: App) -> None:
        """Wrap ``app``."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run ``app``; intercept :class:`RateLimitError`."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        try:
            await self._app(scope, receive, send)
        except RateLimitError as exc:
            await _respond_429(exc, send)


async def _respond_429(exc: RateLimitError, send: Send) -> None:
    """Emit the canonical 429 response."""
    body = json.dumps(
        {
            "error_code": exc.error_code,
            "details": dict(exc.details),
        },
    ).encode("utf-8")
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
    ]
    headers.extend(
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in exc.response_headers().items()
    )
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": headers,
        },
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


__all__ = ["RateLimitHeadersMiddleware"]
