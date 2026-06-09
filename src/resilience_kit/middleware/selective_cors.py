"""ASGI middleware applying CORS only to a subset of paths.

CORS is rarely needed everywhere — admin paths, healthchecks, and
machine-to-machine endpoints want the opposite. This middleware lets
the caller pass a list of path *prefixes* and only injects the CORS
response headers / handles preflight for matching requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from resilience_kit.middleware._asgi import App, Message, Receive, Scope, Send


class SelectiveCorsMiddleware:
    """Inject CORS headers on responses whose path starts with a configured prefix."""

    def __init__(
        self,
        app: App,
        *,
        allow_origins: Sequence[str],
        path_prefixes: Sequence[str],
        allow_methods: Sequence[str] = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
        allow_headers: Sequence[str] = ("Content-Type", "Authorization", "X-Request-Id"),
        max_age_seconds: int = 600,
    ) -> None:
        """Configure CORS.

        Args:
            app: Inner ASGI app.
            allow_origins: List of origins allowed (or ``["*"]`` for any).
            path_prefixes: Only requests whose path starts with one of
                these get CORS headers.
            allow_methods: Methods echoed on preflight.
            allow_headers: Headers echoed on preflight.
            max_age_seconds: ``Access-Control-Max-Age`` value.
        """
        self._app = app
        self._allow_origins = {o.lower() for o in allow_origins}
        self._wildcard = "*" in self._allow_origins
        self._prefixes = tuple(path_prefixes)
        self._allow_methods = ", ".join(allow_methods).encode("latin-1")
        self._allow_headers = ", ".join(allow_headers).encode("latin-1")
        self._max_age = str(max_age_seconds).encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply CORS to matching HTTP requests; otherwise pass through."""
        if scope["type"] != "http" or not self._matches(scope.get("path", "")):
            await self._app(scope, receive, send)
            return

        origin = _header(scope, b"origin")
        allowed = self._is_origin_allowed(origin)

        if scope.get("method") == "OPTIONS":
            await self._respond_preflight(send, origin if allowed else None)
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start" and allowed and origin is not None:
                headers = list(message.get("headers", []))
                headers.append((b"access-control-allow-origin", origin.encode("latin-1")))
                headers.append((b"vary", b"Origin"))
                message["headers"] = headers
            await send(message)

        await self._app(scope, receive, send_with_cors)

    def _matches(self, path: str) -> bool:
        return any(path.startswith(p) for p in self._prefixes)

    def _is_origin_allowed(self, origin: str | None) -> bool:
        if origin is None:
            return False
        return self._wildcard or origin.lower() in self._allow_origins

    async def _respond_preflight(self, send: Send, origin: str | None) -> None:
        if origin is None:
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"text/plain")],
                },
            )
            await send(
                {"type": "http.response.body", "body": b"CORS origin denied"},
            )
            return
        await send(
            {
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"access-control-allow-origin", origin.encode("latin-1")),
                    (b"access-control-allow-methods", self._allow_methods),
                    (b"access-control-allow-headers", self._allow_headers),
                    (b"access-control-max-age", self._max_age),
                    (b"vary", b"Origin"),
                ],
            },
        )
        await send({"type": "http.response.body", "body": b""})


def _header(scope: Scope, name: bytes) -> str | None:
    """Return the first occurrence of ``name`` (case-insensitive)."""
    for raw_name, raw_value in scope.get("headers", []):
        if bytes(raw_name).lower() == name:
            return bytes(raw_value).decode("latin-1")
    return None


__all__ = ["SelectiveCorsMiddleware"]
