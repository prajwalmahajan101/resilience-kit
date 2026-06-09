"""Unit tests for rate_limit_headers and exception_logging middleware."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from resilience_kit.exceptions import (
    DecryptionError,
    ExternalServiceError,
    ExternalTimeoutError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)
from resilience_kit.middleware import (
    ExceptionLoggingMiddleware,
    RateLimitHeadersMiddleware,
)

if TYPE_CHECKING:
    from collections.abc import MutableMapping


def _http_scope() -> MutableMapping[str, Any]:
    return {"type": "http", "method": "GET", "path": "/x", "headers": []}


async def _drive(
    middleware: Any,
    inner: Any,
) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    await middleware(inner)(_http_scope(), receive, send)
    return sent


# --- RateLimitHeadersMiddleware ---------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_middleware_emits_429_with_headers() -> None:
    """The middleware turns ``RateLimitError`` into a canonical 429 response."""

    async def inner(*_a: Any, **_kw: Any) -> None:
        raise RateLimitError(
            limit=60,
            remaining=0,
            reset_at=1_700_000_000,
            retry_after=12.0,
            scope="ip",
        )

    sent = await _drive(RateLimitHeadersMiddleware, inner)
    assert sent[0]["status"] == 429
    headers = {name.decode(): value.decode() for name, value in sent[0]["headers"]}
    assert headers["retry-after"] == "12"
    assert headers["x-ratelimit-limit"] == "60"
    assert headers["x-ratelimit-remaining"] == "0"
    body = json.loads(sent[1]["body"])
    assert body["error_code"] == "RATE_LIMIT_EXCEEDED"


# --- ExceptionLoggingMiddleware ---------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (ValidationError("bad"), 400),
        (
            RateLimitError(
                limit=1,
                remaining=0,
                reset_at=1,
                retry_after=1.0,
            ),
            429,
        ),
        (ServiceUnavailableError("svc"), 503),
        (ExternalTimeoutError("slow"), 504),
        (ExternalServiceError("nope"), 502),
        (DecryptionError("oops"), 500),
    ],
)
@pytest.mark.asyncio
async def test_exception_logging_maps_status_codes(
    exc: Exception,
    expected_status: int,
) -> None:
    """Every kit exception maps to its locked LLD §11 HTTP status."""

    async def inner(*_a: Any, **_kw: Any) -> None:
        raise exc

    sent = await _drive(ExceptionLoggingMiddleware, inner)
    assert sent[0]["status"] == expected_status
    body = json.loads(sent[1]["body"])
    assert body["error_code"] == exc.error_code  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_exception_logging_generic_500_for_non_kit_errors() -> None:
    """Non-kit exceptions become a generic 500; stack trace never leaks to client."""

    async def inner(*_a: Any, **_kw: Any) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    sent = await _drive(ExceptionLoggingMiddleware, inner)
    assert sent[0]["status"] == 500
    body = json.loads(sent[1]["body"])
    assert body["error_code"] == "INTERNAL_ERROR"
    assert "boom" not in body["message"]
