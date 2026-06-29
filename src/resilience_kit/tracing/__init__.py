"""W3C trace-context propagation (Lane C #C3, ADR-0016). Extra: ``[otel]``.

Two pieces:

* :class:`TracingMiddleware` — an ASGI middleware that extracts inbound W3C
  ``traceparent`` context, opens a ``SERVER`` span per request, tags it with the
  kit's ``request_id`` / ``correlation_id`` ContextVars, and records the
  response status. Place it **inside** ``RequestIdMiddleware`` so those
  ContextVars are already bound when the span starts.
* :func:`inject_trace_context` — injects the current span's ``traceparent`` into
  an outbound header map. :class:`~resilience_kit.http_client.client.AsyncAPIClient`
  calls this best-effort, so an inbound→outbound hop produces a connected trace.

Importing this package without the ``[otel]`` extra raises
:class:`~resilience_kit.exceptions.MissingExtraError`. The HTTP client imports it
defensively (swallowing that error), so outbound propagation simply no-ops when
OTel is not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.context import correlation_id, request_id
from resilience_kit.exceptions import MissingExtraError

try:
    from opentelemetry import propagate, trace
    from opentelemetry.trace import SpanKind, Status, StatusCode
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("otel", "resilience-kit[otel]") from exc

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, MutableMapping

    Scope = MutableMapping[str, Any]
    Message = MutableMapping[str, Any]
    Receive = Callable[[], Awaitable[Message]]
    Send = Callable[[Message], Awaitable[None]]
    App = Callable[[Scope, Receive, Send], Awaitable[None]]

#: HTTP status at or above which the server span is marked ERROR.
_SERVER_ERROR_FLOOR = 500


def inject_trace_context(
    headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return ``headers`` with the current trace context injected.

    Uses the globally configured propagator (W3C ``traceparent`` by default).
    When no span is active this injects nothing, so the result is a plain copy
    of ``headers``.

    Args:
        headers: Existing outbound headers, if any.

    Returns:
        A new header dict including ``traceparent`` when a span is active.
    """
    carrier: dict[str, str] = dict(headers) if headers else {}
    propagate.inject(carrier)
    return carrier


class TracingMiddleware:
    """ASGI middleware opening a SERVER span per HTTP request."""

    def __init__(self, app: App, *, tracer_name: str = "resilience_kit") -> None:
        """Wrap ``app``.

        Args:
            app: The inner ASGI app.
            tracer_name: Name of the tracer acquired from the global provider.
        """
        self._app = app
        self._tracer = trace.get_tracer(tracer_name)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Open a span around the HTTP exchange; pass other scopes through.

        Args:
            scope: ASGI scope dict.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        carrier = _headers_dict(scope)
        parent = propagate.extract(carrier)
        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        status_code: dict[str, int] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code["value"] = int(message["status"])
            await send(message)

        with self._tracer.start_as_current_span(
            f"{method} {path}".strip(),
            context=parent,
            kind=SpanKind.SERVER,
        ) as span:
            if method:
                span.set_attribute("http.request.method", method)
            if path:
                span.set_attribute("url.path", path)
            rid = request_id.get()
            if rid is not None:
                span.set_attribute("resilience_kit.request_id", rid)
            cid = correlation_id.get()
            if cid is not None:
                span.set_attribute("resilience_kit.correlation_id", cid)

            await self._app(scope, receive, send_wrapper)

            code = status_code.get("value")
            if code is not None:
                span.set_attribute("http.response.status_code", code)
                if code >= _SERVER_ERROR_FLOOR:
                    span.set_status(Status(StatusCode.ERROR))


def _headers_dict(scope: Scope) -> dict[str, str]:
    """Return a case-folded ``str → str`` view of the request headers.

    ASGI delivers headers as ``(bytes, bytes)`` pairs; both sides are
    decoded to ``str`` here so the dict key is unambiguously hashable.

    Args:
        scope: ASGI scope dict.

    Returns:
        Lower-cased header name → value mapping.
    """
    out: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers", []):
        out[bytes(raw_name).decode("latin-1").lower()] = bytes(raw_value).decode("latin-1")
    return out


__all__ = ["TracingMiddleware", "inject_trace_context"]
