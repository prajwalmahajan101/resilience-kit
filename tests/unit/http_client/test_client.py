"""Unit tests for :class:`resilience_kit.http_client.AsyncAPIClient`."""

from __future__ import annotations

import asyncio
import socket
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("httpx")

import httpx

from resilience_kit.exceptions import (
    ExternalServiceError,
    ExternalTimeoutError,
    ValidationError,
)
from resilience_kit.http_client.client import AsyncAPIClient, OutboundCall


def _public_resolver(host: str, port: int | str | None) -> list[tuple[Any, ...]]:
    return [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 0))]


@pytest.mark.asyncio
async def test_client_validates_url_and_succeeds() -> None:
    """Happy path — validate, pin, dispatch, audit fires."""
    captured: list[OutboundCall] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = AsyncAPIClient(
        service="partner",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        on_outbound=captured.append,
    )
    with patch("resilience_kit.ssrf.guard.socket.getaddrinfo", _public_resolver):
        resp = await client.get("https://partner.example/v1/x")
    assert resp.status_code == 200
    assert captured
    assert captured[0].service == "partner"
    assert captured[0].status == 200
    assert captured[0].error_class is None


@pytest.mark.asyncio
async def test_client_rejects_private_url() -> None:
    """SSRF guard fires before any HTTP dispatch."""
    client = AsyncAPIClient(
        service="partner",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200)),
        ),
    )
    with pytest.raises(ValidationError, match="non-public"):
        await client.get("https://127.0.0.1/admin")


@pytest.mark.asyncio
async def test_client_5xx_becomes_external_timeout_and_audits() -> None:
    """5xx is mapped to the transient family; audit records the status."""
    captured: list[OutboundCall] = []

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="boom")

    client = AsyncAPIClient(
        service="partner-5xx",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        on_outbound=captured.append,
    )
    with (
        patch("resilience_kit.ssrf.guard.socket.getaddrinfo", _public_resolver),
        pytest.raises(ExternalTimeoutError),
    ):
        await client.get("https://partner.example/v1/x")
    assert captured[-1].status == 503
    assert captured[-1].error_class == "ExternalTimeoutError"


@pytest.mark.asyncio
async def test_client_4xx_becomes_external_service_error_when_raised_by_caller() -> None:
    """A caller-raised raise_for_status maps onto ExternalServiceError."""
    captured: list[OutboundCall] = []

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    client = AsyncAPIClient(
        service="partner-4xx",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        on_outbound=captured.append,
    )
    with patch("resilience_kit.ssrf.guard.socket.getaddrinfo", _public_resolver):
        resp = await client.get("https://partner.example/v1/x")
        # 4xx is *not* automatically raised by the client — caller decides.
        # But raise_for_status() inside map_httpx_errors still maps correctly:
        with (
            pytest.raises(ExternalServiceError),
            __import__(
                "resilience_kit.http_client.errors",
                fromlist=["map_httpx_errors"],
            ).map_httpx_errors(url="https://partner.example/v1/x", method="GET", timeout=5.0),
        ):
            resp.raise_for_status()


@pytest.mark.asyncio
async def test_audit_callback_failure_is_swallowed() -> None:
    """An exception from on_outbound never propagates to the caller."""

    def bad_audit(_call: OutboundCall) -> None:
        raise RuntimeError("audit broken")

    client = AsyncAPIClient(
        service="partner-audit",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200)),
        ),
        on_outbound=bad_audit,
    )
    with patch("resilience_kit.ssrf.guard.socket.getaddrinfo", _public_resolver):
        resp = await client.get("https://partner.example/v1/x")
    assert resp.status_code == 200


def test_request_sync_outside_loop() -> None:
    """No running loop → sync mirror drives a private one."""
    client = AsyncAPIClient(
        service="partner-sync",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200)),
        ),
    )
    with patch("resilience_kit.ssrf.guard.socket.getaddrinfo", _public_resolver):
        resp = client.request_sync("GET", "https://partner.example/v1/x")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_request_sync_inside_loop_raises() -> None:
    """Calling request_sync from inside a loop is a programmer error."""
    client = AsyncAPIClient(
        service="partner-sync-error",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200)),
        ),
    )
    with pytest.raises(RuntimeError, match="running event loop"):
        client.request_sync("GET", "https://partner.example/")


@pytest.mark.asyncio
async def test_verb_shortcuts_delegate_to_request() -> None:
    """get / post / put / patch / delete each set the method correctly."""
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.method)
        return httpx.Response(200)

    client = AsyncAPIClient(
        service="partner-verbs",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with patch("resilience_kit.ssrf.guard.socket.getaddrinfo", _public_resolver):
        await client.get("https://partner.example/")
        await client.post("https://partner.example/")
        await client.put("https://partner.example/")
        await client.patch("https://partner.example/")
        await client.delete("https://partner.example/")
    assert seen == ["GET", "POST", "PUT", "PATCH", "DELETE"]


# Avoid unused-import warning for asyncio (it is needed implicitly via pytest-asyncio).
_ = asyncio
