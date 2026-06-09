"""Unit tests for body_limit / security_headers / selective_cors middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from resilience_kit.middleware import (
    BodyLimitMiddleware,
    SecurityHeadersMiddleware,
    SelectiveCorsMiddleware,
)

if TYPE_CHECKING:
    from collections.abc import MutableMapping


def _http_scope(
    *,
    method: str = "GET",
    path: str = "/x",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> MutableMapping[str, Any]:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
    }


async def _capture_response(
    middleware: Any,
    scope: MutableMapping[str, Any],
    request_chunks: list[bytes] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    request_chunks = request_chunks or [b""]
    sent: list[dict[str, Any]] = []
    received: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        if not request_chunks:
            return {"type": "http.request", "body": b"", "more_body": False}
        chunk = request_chunks.pop(0)
        more = bool(request_chunks)
        return {"type": "http.request", "body": chunk, "more_body": more}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def app(scope_in: Any, receive_in: Any, send_in: Any) -> None:
        msg = await receive_in()
        received.append(dict(msg))
        await send_in(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            },
        )
        await send_in({"type": "http.response.body", "body": b"ok"})

    bound = middleware(app)
    await bound(scope, receive, send)
    return sent, received


# --- BodyLimitMiddleware -----------------------------------------------------


@pytest.mark.asyncio
async def test_body_limit_rejects_oversized_content_length() -> None:
    """``Content-Length`` over the cap → immediate 413, app not called."""
    scope = _http_scope(headers=[(b"content-length", b"100")])
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    app_called = False

    async def app(*_a: Any, **_kw: Any) -> None:
        nonlocal app_called
        app_called = True

    await BodyLimitMiddleware(app, max_bytes=10)(scope, receive, send)
    assert sent[0]["status"] == 413
    assert app_called is False


@pytest.mark.asyncio
async def test_body_limit_lets_small_requests_through() -> None:
    """Within the limit, the inner app sees the body normally."""

    async def app(scope: Any, receive: Any, send: Any) -> None:
        msg = await receive()
        assert msg["body"] == b"small"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent: list[dict[str, Any]] = []

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"small", "more_body": False}

    await BodyLimitMiddleware(app, max_bytes=100)(_http_scope(), receive, send)
    assert sent[0]["status"] == 200


# --- SecurityHeadersMiddleware ----------------------------------------------


@pytest.mark.asyncio
async def test_security_headers_attaches_defaults() -> None:
    """Default header set is appended on every response."""
    sent, _ = await _capture_response(SecurityHeadersMiddleware, _http_scope())
    start = sent[0]
    names = {name.decode() for name, _ in start["headers"]}
    assert "x-content-type-options" in names
    assert "x-frame-options" in names
    assert "strict-transport-security" in names


@pytest.mark.asyncio
async def test_security_headers_overrides_and_extras() -> None:
    """Overrides replace and extras add."""

    def factory(app: Any) -> Any:
        return SecurityHeadersMiddleware(
            app,
            overrides={"X-Frame-Options": "SAMEORIGIN"},
            extra={"X-Custom": "yes"},
        )

    sent, _ = await _capture_response(factory, _http_scope())
    headers = dict(sent[0]["headers"])
    assert headers[b"x-frame-options"] == b"SAMEORIGIN"
    assert headers[b"x-custom"] == b"yes"


# --- SelectiveCorsMiddleware -------------------------------------------------


def _cors_factory(allow_origins: list[str], prefixes: list[str]) -> Any:
    def factory(app: Any) -> Any:
        return SelectiveCorsMiddleware(
            app,
            allow_origins=allow_origins,
            path_prefixes=prefixes,
        )

    return factory


@pytest.mark.asyncio
async def test_cors_only_applies_on_matching_prefix() -> None:
    """Non-matching path → no CORS header on the response."""
    scope = _http_scope(path="/internal/x", headers=[(b"origin", b"https://app.example")])
    sent, _ = await _capture_response(
        _cors_factory(["https://app.example"], ["/api"]),
        scope,
    )
    names = {name.decode() for name, _ in sent[0]["headers"]}
    assert "access-control-allow-origin" not in names


@pytest.mark.asyncio
async def test_cors_attaches_on_matching_prefix() -> None:
    """Matching path + allowed origin → CORS allow-origin header set."""
    scope = _http_scope(
        path="/api/v1/x",
        headers=[(b"origin", b"https://app.example")],
    )
    sent, _ = await _capture_response(
        _cors_factory(["https://app.example"], ["/api"]),
        scope,
    )
    headers = dict(sent[0]["headers"])
    assert headers[b"access-control-allow-origin"] == b"https://app.example"


@pytest.mark.asyncio
async def test_cors_preflight_204() -> None:
    """OPTIONS on a matching path → 204 preflight with allow-method/header."""
    scope = _http_scope(
        method="OPTIONS",
        path="/api/v1/x",
        headers=[(b"origin", b"https://app.example")],
    )
    sent: list[dict[str, Any]] = []

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def app(*_a: Any, **_kw: Any) -> None:
        msg = "preflight should not reach app"
        raise AssertionError(msg)

    cors = SelectiveCorsMiddleware(
        app,
        allow_origins=["https://app.example"],
        path_prefixes=["/api"],
    )
    await cors(scope, receive, send)
    assert sent[0]["status"] == 204
    headers = dict(sent[0]["headers"])
    assert headers[b"access-control-allow-origin"] == b"https://app.example"
    assert b"access-control-allow-methods" in headers
