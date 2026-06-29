"""Unit tests for the tracing middleware + propagation (Lane C #C3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("opentelemetry")

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from resilience_kit.context import bind
from resilience_kit.tracing import TracingMiddleware, inject_trace_context

if TYPE_CHECKING:
    from collections.abc import Iterator

_exporter = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _tracer_provider() -> None:
    """Install a module-local tracer provider feeding an in-memory exporter."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_exporter))
    trace.set_tracer_provider(provider)


@pytest.fixture(autouse=True)
def _clear_spans() -> Iterator[None]:
    _exporter.clear()
    yield
    _exporter.clear()


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "GET",
        "path": "/widgets",
        "headers": headers or [],
    }


async def _ok_app(scope: Any, receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def _drain(messages: list[dict[str, Any]]) -> None:
    pass


def _collect_sends() -> tuple[list[dict[str, Any]], Any]:
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    return sent, send


async def test_server_span_created_with_request_id() -> None:
    """A request opens one SERVER span tagged with the kit request_id."""
    _sent, send = _collect_sends()
    mw = TracingMiddleware(_ok_app)
    with bind(request_id_value="rid-123", correlation_id_value="cid-456"):
        await mw(_http_scope(), _drain, send)

    spans = _exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.kind is trace.SpanKind.SERVER
    assert span.attributes["resilience_kit.request_id"] == "rid-123"
    assert span.attributes["resilience_kit.correlation_id"] == "cid-456"
    assert span.attributes["http.response.status_code"] == 200


async def test_inbound_traceparent_links_parent() -> None:
    """An inbound W3C traceparent becomes the span's parent trace."""
    trace_id_hex = "0af7651916cd43dd8448eb211c80319c"
    parent = f"00-{trace_id_hex}-b7ad6b7169203331-01"
    _sent, send = _collect_sends()
    mw = TracingMiddleware(_ok_app)
    await mw(
        _http_scope(headers=[(b"traceparent", parent.encode())]),
        _drain,
        send,
    )
    span = _exporter.get_finished_spans()[0]
    assert format(span.context.trace_id, "032x") == trace_id_hex


async def test_5xx_marks_span_error() -> None:
    """A 5xx response sets the span status to ERROR."""

    async def _err_app(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 503, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    _sent, send = _collect_sends()
    mw = TracingMiddleware(_err_app)
    await mw(_http_scope(), _drain, send)
    span = _exporter.get_finished_spans()[0]
    assert span.status.status_code is trace.StatusCode.ERROR


def test_inject_trace_context_adds_traceparent_within_span() -> None:
    """inject_trace_context emits a traceparent while a span is active."""
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("outbound"):
        headers = inject_trace_context({"x-existing": "1"})
    assert "traceparent" in headers
    assert headers["x-existing"] == "1"


def test_non_http_scope_passes_through() -> None:
    """Lifespan / websocket scopes are not traced."""

    async def _run() -> bool:
        called = {"v": False}

        async def _inner(scope: Any, receive: Any, send: Any) -> None:
            called["v"] = True

        mw = TracingMiddleware(_inner)
        await mw({"type": "lifespan"}, _drain, lambda m: None)
        return called["v"]

    import asyncio  # noqa: PLC0415

    assert asyncio.run(_run()) is True
    assert _exporter.get_finished_spans() == ()
