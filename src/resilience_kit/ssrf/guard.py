"""SSRF guard — URL resolution, IP validation, and outbound allow-list.

Two layers, called in order by :class:`~resilience_kit.http_client.AsyncAPIClient`:

1. :func:`resolve_and_validate` parses the URL, rejects non-``http``/``https``
   schemes, resolves the hostname via :func:`socket.getaddrinfo`, and
   rejects any URL that resolves to a non-public address (RFC1918,
   loopback, link-local, multicast, reserved, unspecified). It returns
   the resolved IP set so the caller can **pin** those IPs across the
   validate → request boundary (see :mod:`resilience_kit.http_client.dns_pin`)
   — together they close the classic DNS-rebinding TOCTOU where a
   malicious zone returns a public IP at validation time and a private
   one at request time.

2. :func:`assert_allowed_url` checks the URL host against
   ``settings.ssrf.outbound_allowlist`` — a positive list (exact host or
   ``.suffix`` form) that blocks legitimate public hosts the service was
   never supposed to call. ``["*"]`` (the default) is permissive.

The thin :func:`assert_public_url` shim keeps the historical entry point
for callers that don't need the pinned IP set (e.g. save-time validators).

Disabled per-layer by ``settings.ssrf.block_private_ips=False`` (used by
tests that hit localhost mock servers) and the allow-list by leaving
it at ``["*"]``.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

from resilience_kit.exceptions import ValidationError
from resilience_kit.runtime import get_settings
from resilience_kit.ssrf._ipchecks import classify_non_public

logger = logging.getLogger(__name__)


def safe_host(url: str) -> str:
    """Extract a logging-safe hostname (no port / path / query) from ``url``.

    Args:
        url: Any URL string.

    Returns:
        The hostname, or ``"external service"`` if parsing fails — so the
        log line still reads sensibly without leaking the full URL.
    """
    try:
        return urlparse(url).hostname or "external service"
    except ValueError:
        return "external service"


def resolve_and_validate(url: str, *, strict: bool = True) -> set[str]:
    """Validate ``url`` and return the resolved IP set for pinning.

    ``strict=True`` (default; used by the HTTP-call path) rejects an
    unresolvable hostname. ``strict=False`` (used by save-time validators)
    accepts unresolvable hostnames so transient DNS failure does not
    block legitimate partner configuration; the HTTP-call path still
    gates the actual outbound request.

    Args:
        url: Outbound URL to validate.
        strict: When ``True`` an unresolvable hostname is an error.

    Returns:
        The set of resolved IPs (literal address when the host is an
        IP literal). Empty set when validation is disabled or the host
        did not resolve under ``strict=False``.

    Raises:
        ValidationError: URL scheme is not ``http``/``https``, no
            hostname is present, hostname cannot be resolved (when
            ``strict=True``), or resolves to a private / loopback /
            link-local / reserved / multicast / unspecified address.
    """
    if not get_settings().ssrf.block_private_ips:
        return set()

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            f"URL scheme '{parsed.scheme}' is not allowed (only http/https).",
            details={"url": url, "scheme": parsed.scheme},
        )
    host = parsed.hostname
    if not host:
        raise ValidationError("URL has no hostname.", details={"url": url})

    addrs = _resolve(host, url=url, strict=strict)
    if not addrs:
        return set()

    for addr in addrs:
        reason = classify_non_public(addr)
        if reason is not None:
            raise ValidationError(
                f"URL resolves to a non-public address ({addr}: {reason}).",
                details={"url": url, "host": host, "address": addr, "reason": reason},
            )
    return addrs


def _resolve(host: str, *, url: str, strict: bool) -> set[str]:
    """Return ``{addr, ...}`` for ``host`` — literal or resolved.

    Args:
        host: Hostname or IP literal extracted from the URL.
        url: Original URL — included in the error payload.
        strict: When ``True`` an unresolvable hostname raises.

    Returns:
        Resolved address set; empty set when DNS fails under ``strict=False``.

    Raises:
        ValidationError: ``strict=True`` and ``host`` cannot be resolved.
    """
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return {str(literal)}

    try:
        return {str(info[4][0]) for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        if strict:
            raise ValidationError(
                f"URL hostname '{host}' could not be resolved.",
                details={"url": url, "host": host},
            ) from exc
        logger.info(
            "SSRF validator: %s did not resolve (strict=False, accepting).",
            host,
        )
        return set()


def assert_public_url(url: str, *, strict: bool = True) -> None:
    """Raise :class:`ValidationError` if ``url`` resolves to a non-public address.

    Thin shim over :func:`resolve_and_validate` for callers that do not
    need the resolved IP set (e.g. save-time validators).

    Args:
        url: Outbound URL to validate.
        strict: When ``True`` an unresolvable hostname is an error.

    Raises:
        ValidationError: See :func:`resolve_and_validate`.
    """
    resolve_and_validate(url, strict=strict)


def assert_allowed_url(url: str) -> None:
    """Reject ``url`` when its host is not in ``settings.ssrf.outbound_allowlist``.

    Defence-in-depth alongside :func:`resolve_and_validate`. The SSRF
    guard blocks private IPs; the allow-list blocks legitimate public
    hosts the service was never supposed to call (data-exfiltration via
    a misconfigured partner URL, accidental request to a typo'd domain).

    Allow-list entries:

    * ``"*"`` — wildcard, allow anything. Use in local / dev.
    * ``"example.com"`` — exact host match.
    * ``".example.com"`` — suffix match (any subdomain *and* the apex).

    Empty list = permissive (matches the historical behaviour). Prod and
    UAT should set the field explicitly per environment.

    Args:
        url: Outbound URL to validate.

    Raises:
        ValidationError: Host is not in the allow-list.
    """
    allow = list(get_settings().ssrf.outbound_allowlist or [])
    if not allow or "*" in allow:
        return

    host = (urlparse(url).hostname or "").lower()
    if not host:
        raise ValidationError(
            "URL has no hostname.",
            details={"url": url},
        )

    for entry in (e.lower() for e in allow):
        if entry.startswith("."):
            if host == entry[1:] or host.endswith(entry):
                return
        elif host == entry:
            return
    raise ValidationError(
        f"Outbound URL host '{host}' is not in outbound_allowlist.",
        details={"url": url, "host": host, "allowlist": allow},
    )
