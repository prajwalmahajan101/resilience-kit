"""SSRF guard — outbound URL validation + allow-list (LLD §5).

The guard rejects URLs that resolve to non-public addresses (RFC1918 /
loopback / link-local / multicast / reserved / unspecified) and enforces
a per-environment outbound allow-list. It returns the resolved IP set so
:mod:`resilience_kit.http_client` can pin DNS across the validate →
connect boundary, closing the classic DNS-rebinding TOCTOU.
"""

from __future__ import annotations

from resilience_kit.ssrf.guard import (
    assert_allowed_url,
    assert_public_url,
    resolve_and_validate,
    safe_host,
)

__all__ = [
    "assert_allowed_url",
    "assert_public_url",
    "resolve_and_validate",
    "safe_host",
]
