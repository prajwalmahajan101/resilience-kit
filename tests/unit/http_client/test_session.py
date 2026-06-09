"""Unit tests for :mod:`resilience_kit.http_client.session`."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")

import httpx

from resilience_kit.http_client.dns_pin import PinnedHTTPTransport
from resilience_kit.http_client.session import pinned_httpx_client


def test_pinned_httpx_client_installs_pinned_transport() -> None:
    """Default factory installs the pinned transport."""
    client = pinned_httpx_client()
    assert isinstance(client._transport, PinnedHTTPTransport)


def test_pinned_httpx_client_respects_caller_transport() -> None:
    """Caller-supplied transport wins — escape hatch for advanced cases."""
    custom = httpx.MockTransport(lambda req: httpx.Response(204))
    client = pinned_httpx_client(transport=custom)
    assert client._transport is custom


def test_pinned_httpx_client_forwards_kwargs() -> None:
    """``timeout``, ``headers`` etc. flow through to the underlying client."""
    client = pinned_httpx_client(timeout=httpx.Timeout(2.0))
    assert client.timeout.connect == pytest.approx(2.0)
