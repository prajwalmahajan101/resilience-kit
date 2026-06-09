"""Outbound HTTP client — SSRF + DNS-pin + breaker + retry + audit (LLD §5).

Requires the ``http`` extra (``pip install
'prajwal-resilience-kit[http]'``). Importing any submodule without
``httpx`` installed raises :class:`~resilience_kit.exceptions.MissingExtraError`
at import time.
"""

from __future__ import annotations

from resilience_kit.http_client.auth import BasicAuth, BearerAuth, HMACAuth
from resilience_kit.http_client.client import AsyncAPIClient, OutboundCall
from resilience_kit.http_client.dns_pin import PinnedHTTPTransport, pinned, pinned_dns
from resilience_kit.http_client.errors import map_httpx_errors, raise_for_server_error
from resilience_kit.http_client.session import (
    pinned_httpx_client,
    pinned_requests_session,
)

__all__ = [
    "AsyncAPIClient",
    "BasicAuth",
    "BearerAuth",
    "HMACAuth",
    "OutboundCall",
    "PinnedHTTPTransport",
    "map_httpx_errors",
    "pinned",
    "pinned_dns",
    "pinned_httpx_client",
    "pinned_requests_session",
    "raise_for_server_error",
]
