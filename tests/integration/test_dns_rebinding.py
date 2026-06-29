"""DNS-rebinding TOCTOU test — M3 exit gate.

A malicious zone returns a public IP at validate time and a private IP
at connect time. Without the pin, the SSRF guard's resolution is
discarded and the actual connect (a second :func:`socket.getaddrinfo`)
goes to the private IP. With the pin installed by
:class:`AsyncAPIClient`, the request URL is rewritten to **only** the
public IP the validator approved — so even if a second resolution would
return a private IP, the connect never happens against it.

The test mocks :func:`socket.getaddrinfo` so the first call (driven by
:func:`resilience_kit.ssrf.guard.resolve_and_validate`) returns
``8.8.8.8`` and the second (the would-be connect) returns
``127.0.0.1``. It then asserts that the request handed to the underlying
transport carries the pinned ``8.8.8.8`` host — not ``127.0.0.1``.
"""

from __future__ import annotations

import socket
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("httpx")

import httpx

from resilience_kit.exceptions import ValidationError
from resilience_kit.http_client.client import AsyncAPIClient
from resilience_kit.http_client.dns_pin import PinnedHTTPTransport, _pick_pinned_ip
from resilience_kit.http_client.session import pinned_httpx_client

pytestmark = pytest.mark.integration


class _RebindingResolver:
    """``getaddrinfo`` stand-in: public IP first, private IP after.

    Mimics a zone whose A record changes between the SSRF validator's
    lookup and the underlying transport's lookup.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(
        self,
        host: str,
        port: int | str | None,
        *_a: Any,
        **_kw: Any,
    ) -> list[tuple[Any, ...]]:
        """Return public IP on the first call, private IP after."""
        self.calls += 1
        ip = "8.8.8.8" if self.calls == 1 else "127.0.0.1"
        return [(socket.AF_INET, 0, 0, "", (ip, 0))]


class _CapturingPinnedTransport(PinnedHTTPTransport):
    """Pinned transport that records the dispatched URL host.

    The test uses this in place of the real network-bound parent so it
    can assert what host the request would have connected to, without
    actually opening a socket.
    """

    captured_host: str | None = None
    captured_sni: str | None = None
    captured_host_header: str | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Run the pin rewrite, then capture and short-circuit."""
        original_host = request.url.host
        pinned_ip = _pick_pinned_ip(original_host)
        if pinned_ip is not None:
            request.headers.setdefault("Host", original_host)
            request.extensions["sni_hostname"] = original_host
            request.url = request.url.copy_with(host=pinned_ip)
        type(self).captured_host = request.url.host
        type(self).captured_sni = request.extensions.get("sni_hostname")
        type(self).captured_host_header = request.headers.get("Host")
        return httpx.Response(200, text="ok")


@pytest.mark.asyncio
async def test_dns_rebinding_attack_is_blocked_by_pin() -> None:
    """TOCTOU rebind: 1st lookup public, 2nd lookup private — pin wins.

    The assertion that proves the gate: the host the transport actually
    dispatched to is the pinned public ``8.8.8.8``, not the private
    ``127.0.0.1`` that the 2nd resolution would have returned.
    """
    resolver = _RebindingResolver()
    _CapturingPinnedTransport.captured_host = None
    _CapturingPinnedTransport.captured_sni = None
    _CapturingPinnedTransport.captured_host_header = None

    transport = _CapturingPinnedTransport()
    client = AsyncAPIClient(
        service="rebind-test",
        client=httpx.AsyncClient(transport=transport),
    )
    with patch("resilience_kit.ssrf.guard.socket.getaddrinfo", resolver):
        resp = await client.get("https://partner.example/v1/x")

    assert resp.status_code == 200
    # Exit-gate: connect went to the pinned public IP, not the rebound private one.
    assert _CapturingPinnedTransport.captured_host == "8.8.8.8"
    assert _CapturingPinnedTransport.captured_host != "127.0.0.1"
    # TLS / Host routing is preserved so cert verification and upstream routing still work.
    assert _CapturingPinnedTransport.captured_sni == "partner.example"
    assert _CapturingPinnedTransport.captured_host_header == "partner.example"


@pytest.mark.asyncio
async def test_dns_rebinding_when_validator_sees_private_is_rejected() -> None:
    """Companion check: if the validator's lookup returns private, request is denied.

    Defense-in-depth — the pin protects against a rebind happening after
    validation; this proves the validator itself blocks a zone that's
    already private at validation time.
    """

    def always_private(*_a: Any, **_kw: Any) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, 0, 0, "", ("127.0.0.1", 0))]

    transport = httpx.MockTransport(
        lambda _r: pytest.fail("Transport must not be called when SSRF blocks"),
    )
    client = AsyncAPIClient(
        service="rebind-test-2",
        client=httpx.AsyncClient(transport=transport),
    )
    with (
        patch("resilience_kit.ssrf.guard.socket.getaddrinfo", always_private),
        pytest.raises(ValidationError, match="non-public"),
    ):
        await client.get("https://partner.example/v1/x")


@pytest.mark.asyncio
async def test_pinned_client_does_not_follow_redirects() -> None:
    """#B1: a 302 to a private host is surfaced, not auto-followed.

    Auto-following resolves the redirect target through normal DNS, never
    re-validated against SSRF and never re-pinned — an open redirect to a
    private IP or cloud metadata would defeat the pin (CWE-918 + CWE-601).
    """
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://10.0.0.5/internal"})

    async with pinned_httpx_client(transport=httpx.MockTransport(handler)) as client:
        resp = await client.get("https://partner.example/start")

    assert resp.status_code == 302
    assert resp.headers["location"] == "http://10.0.0.5/internal"
    # The redirect was returned to the caller, not chased — only one request fired.
    assert calls == ["https://partner.example/start"]


def test_pinned_client_refuses_follow_redirects_true() -> None:
    """#B1: opting into auto-redirects is refused loudly, not silently overridden."""
    with pytest.raises(ValueError, match="follow_redirects=True"):
        pinned_httpx_client(follow_redirects=True)
