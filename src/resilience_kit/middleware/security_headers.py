"""ASGI middleware that injects baseline security headers on every response.

The defaults are the conservative set the boilerplates have shipped for
two years: deny framing, no MIME sniffing, no referer leakage,
strict-transport-security on HTTPS responses, and a permissive but
explicit Permissions-Policy.

Customise by passing ``overrides=`` or ``extra=`` — overrides replace a
default header, extras add new ones.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from resilience_kit.middleware._asgi import App, Message, Receive, Scope, Send

DEFAULTS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


class SecurityHeadersMiddleware:
    """Attach security headers to every HTTP response."""

    def __init__(
        self,
        app: App,
        *,
        overrides: Mapping[str, str] | None = None,
        extra: Mapping[str, str] | None = None,
    ) -> None:
        """Configure the header set.

        Args:
            app: Inner ASGI app.
            overrides: Replace specific default headers (last-write-wins).
            extra: Additional headers to attach.
        """
        merged: dict[str, str] = dict(DEFAULTS)
        if overrides:
            merged.update(overrides)
        if extra:
            merged.update(extra)
        self._app = app
        self._headers: list[tuple[bytes, bytes]] = [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in merged.items()
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Attach the configured headers on ``http.response.start``."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                merged = list(message.get("headers", []))
                merged.extend(self._headers)
                message["headers"] = merged
            await send(message)

        await self._app(scope, receive, send_with_headers)


__all__ = ["DEFAULTS", "SecurityHeadersMiddleware"]
