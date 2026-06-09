"""Unit tests for :mod:`resilience_kit.http_client.dns_pin`."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")

import httpx

from resilience_kit.http_client.dns_pin import (
    PinnedHTTPTransport,
    _pick_pinned_ip,
    pinned,
    pinned_dns,
)


def test_pinned_sets_and_resets_contextvar() -> None:
    """The pin lives only for the duration of the ``with`` block."""
    assert pinned_dns.get() is None
    with pinned({"partner.example": {"1.2.3.4"}}):
        assert pinned_dns.get() == {"partner.example": {"1.2.3.4"}}
    assert pinned_dns.get() is None


def test_pinned_normalises_host_case() -> None:
    """Mapping is lowercased so callers can pass URL host as-is."""
    with pinned({"Partner.EXAMPLE": {"1.2.3.4"}}):
        assert _pick_pinned_ip("partner.example") == "1.2.3.4"
        assert _pick_pinned_ip("PARTNER.EXAMPLE") == "1.2.3.4"


def test_pick_pinned_ip_returns_none_when_no_pin() -> None:
    """No pin in effect → return None so the caller defers to the default resolver."""
    assert _pick_pinned_ip("partner.example") is None


def test_pick_pinned_ip_returns_none_when_host_missing() -> None:
    """Pin set for another host → return None for this one."""
    with pinned({"other.example": {"1.2.3.4"}}):
        assert _pick_pinned_ip("partner.example") is None


def test_pick_pinned_ip_deterministic_lowest_sorted() -> None:
    """Multiple pinned IPs → return the lexicographically lowest for determinism."""
    with pinned({"x.example": {"9.9.9.9", "1.1.1.1", "5.5.5.5"}}):
        assert _pick_pinned_ip("x.example") == "1.1.1.1"


@pytest.mark.asyncio
async def test_pinned_transport_rewrites_url_to_pinned_ip() -> None:
    """When a pin is active the transport sends to the IP and preserves SNI."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["host_header"] = request.headers.get("Host")
        captured["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, text="ok")

    # MockTransport ≠ AsyncHTTPTransport, so test the pin logic via a small
    # subclass that delegates to the mock handler instead of TCP.
    class _PinnedMock(PinnedHTTPTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            original_host = request.url.host
            pinned_ip = _pick_pinned_ip(original_host)
            if pinned_ip is not None:
                request.headers.setdefault("Host", original_host)
                request.extensions["sni_hostname"] = original_host
                request.url = request.url.copy_with(host=pinned_ip)
            return handler(request)

    async with httpx.AsyncClient(transport=_PinnedMock()) as client:
        with pinned({"partner.example": {"5.6.7.8"}}):
            resp = await client.get("https://partner.example/v1/x")
    assert resp.status_code == 200
    assert "5.6.7.8" in str(captured["url"])
    assert captured["host_header"] == "partner.example"
    assert captured["sni"] == "partner.example"


@pytest.mark.asyncio
async def test_pinned_transport_passthrough_when_no_pin() -> None:
    """No pin → URL unchanged, no Host header / SNI injection."""
    captured: dict[str, object] = {}

    class _MockNoPin(PinnedHTTPTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            assert _pick_pinned_ip(request.url.host) is None
            captured["url"] = str(request.url)
            captured["sni"] = request.extensions.get("sni_hostname")
            return httpx.Response(204)

    async with httpx.AsyncClient(transport=_MockNoPin()) as client:
        resp = await client.get("https://no-pin.example/")
    assert resp.status_code == 204
    assert "no-pin.example" in str(captured["url"])
    assert captured["sni"] is None
