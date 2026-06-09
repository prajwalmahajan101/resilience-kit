"""Unit tests for :class:`resilience_kit.middleware.RequestIdMiddleware`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from resilience_kit.context import correlation_id, request_id
from resilience_kit.middleware import RequestIdMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, MutableMapping


Scope = "MutableMapping[str, Any]"


def _scope(headers: list[tuple[bytes, bytes]] | None = None) -> MutableMapping[str, Any]:
    return {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": headers or [],
    }


async def _empty_receive() -> dict[str, Any]:
    return {"type": "http.request"}


@pytest.mark.asyncio
async def test_generates_request_id_when_missing() -> None:
    """When no header is supplied, a new request id is generated and bound."""
    captured: dict[str, Any] = {}
    response_headers: list[tuple[bytes, bytes]] = []

    async def app(
        scope: Any,
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[Any], Awaitable[None]],
    ) -> None:
        captured["rid"] = request_id.get()
        captured["cid"] = correlation_id.get()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            },
        )

    async def send(message: Any) -> None:
        if message["type"] == "http.response.start":
            response_headers.extend(message["headers"])

    await RequestIdMiddleware(app)(_scope(), _empty_receive, send)
    assert captured["rid"] is not None
    assert captured["cid"] == captured["rid"]  # correlation falls back to request id.
    rid_header = dict(response_headers).get(b"x-request-id")
    assert rid_header is not None
    assert rid_header.decode() == captured["rid"]


@pytest.mark.asyncio
async def test_uses_incoming_headers() -> None:
    """Incoming X-Request-Id / X-Correlation-Id win over generated ones."""
    captured: dict[str, Any] = {}

    async def app(
        scope: Any,
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[Any], Awaitable[None]],
    ) -> None:
        captured["rid"] = request_id.get()
        captured["cid"] = correlation_id.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(_message: Any) -> None:
        return None

    scope = _scope(
        headers=[
            (b"X-Request-Id", b"rq-inbound"),
            (b"X-Correlation-Id", b"corr-inbound"),
        ],
    )
    await RequestIdMiddleware(app)(scope, _empty_receive, send)
    assert captured["rid"] == "rq-inbound"
    assert captured["cid"] == "corr-inbound"


@pytest.mark.asyncio
async def test_lifespan_scope_pass_through() -> None:
    """Non-HTTP scopes (lifespan / websocket) are forwarded without binding."""
    invoked = False

    async def app(
        scope: Any,
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[Any], Awaitable[None]],
    ) -> None:
        nonlocal invoked
        invoked = True

    async def send(_message: Any) -> None:
        return None

    await RequestIdMiddleware(app)(
        {"type": "lifespan", "headers": []},
        _empty_receive,
        send,
    )
    assert invoked
    # No ContextVar leakage.
    assert request_id.get() is None
    assert correlation_id.get() is None
