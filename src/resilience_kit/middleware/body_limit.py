"""ASGI middleware that rejects requests exceeding a body-size limit.

Reads the inbound ``Content-Length`` header when present and rejects up-
front with HTTP 413 (``Payload Too Large``). For requests without
``Content-Length`` (chunked / streaming), the middleware also caps the
accumulated body size streamed through ``receive`` so a slow / malicious
client cannot tip the worker over.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from resilience_kit.middleware._asgi import App, Receive, Scope, Send


class BodyLimitMiddleware:
    """Reject requests whose body exceeds ``max_bytes``."""

    def __init__(self, app: App, *, max_bytes: int = 1_048_576) -> None:
        """Wrap ``app`` and set the limit.

        Args:
            app: Inner ASGI app.
            max_bytes: Hard cap (defaults to 1 MiB). Requests exceeding
                this get an immediate ``413`` response.
        """
        self._app = app
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply the limit on HTTP scopes; pass everything else through."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared is not None and declared > self._max:
            await _send_413(send)
            return

        seen = 0

        async def capped_receive() -> dict[str, object]:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if isinstance(body, (bytes, bytearray)):
                    seen += len(body)
                    if seen > self._max:
                        # The body is over budget mid-stream — close the
                        # request by reporting "no more body" so the
                        # downstream app handles the disconnect cleanly.
                        return {"type": "http.disconnect"}
            return dict(message)

        await self._app(scope, capped_receive, send)


def _content_length(scope: Scope) -> int | None:
    """Read the inbound ``Content-Length`` header if any (case-insensitive)."""
    for raw_name, raw_value in scope.get("headers", []):
        name = bytes(raw_name).lower()
        if name == b"content-length":
            try:
                return int(bytes(raw_value))
            except ValueError:
                return None
    return None


async def _send_413(send: Send) -> None:
    """Emit a minimal ``413 Payload Too Large`` response."""
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        },
    )
    await send(
        {
            "type": "http.response.body",
            "body": b"Payload Too Large",
            "more_body": False,
        },
    )


__all__ = ["BodyLimitMiddleware"]
