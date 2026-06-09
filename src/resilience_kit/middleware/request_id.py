"""ASGI middleware that seeds the kit's request_id / correlation_id ContextVars.

On every inbound HTTP request:

* Read the configured request-id header (default ``X-Request-Id``). If
  missing, generate a fresh hex id via :func:`new_request_id`.
* Read the configured correlation-id header (default
  ``X-Correlation-Id``). If missing, fall back to the request id.
* Bind both into :mod:`resilience_kit.context` ContextVars for the
  duration of the call.
* Echo both headers on the outgoing response so callers can correlate
  request/response across logs.

Non-HTTP scopes (lifespan, websocket) are passed through unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.context import bind, new_request_id

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, MutableMapping

    Scope = MutableMapping[str, Any]
    Message = MutableMapping[str, Any]
    Receive = Callable[[], Awaitable[Message]]
    Send = Callable[[Message], Awaitable[None]]
    App = Callable[[Scope, Receive, Send], Awaitable[None]]


class RequestIdMiddleware:
    """ASGI middleware seeding the kit's request-id ContextVars."""

    def __init__(
        self,
        app: App,
        *,
        header: str = "x-request-id",
        correlation_header: str = "x-correlation-id",
    ) -> None:
        """Wrap ``app`` and configure the header names.

        Args:
            app: The inner ASGI app.
            header: Inbound + outbound header carrying the request id.
            correlation_header: Inbound + outbound header carrying the
                correlation id.
        """
        self._app = app
        self._header = header.lower().encode("latin-1")
        self._correlation_header = correlation_header.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process one ASGI event.

        Args:
            scope: ASGI scope dict.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = _headers_dict(scope)
        rid = headers.get(self._header) or new_request_id()
        cid = headers.get(self._correlation_header) or rid

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                merged = list(message.get("headers", []))
                merged.append((self._header, rid.encode("latin-1")))
                merged.append((self._correlation_header, cid.encode("latin-1")))
                message["headers"] = merged
            await send(message)

        with bind(request_id_value=rid, correlation_id_value=cid):
            await self._app(scope, receive, send_with_headers)


def _headers_dict(scope: Scope) -> dict[bytes, str]:
    """Return a case-folded ``bytes → str`` view of the request headers."""
    out: dict[bytes, str] = {}
    for name, value in scope.get("headers", []):
        out[bytes(name).lower()] = bytes(value).decode("latin-1")
    return out


__all__ = ["RequestIdMiddleware"]
