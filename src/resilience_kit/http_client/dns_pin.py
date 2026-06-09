"""DNS pinning across the validate → connect boundary (LLD §5).

The :class:`~resilience_kit.ssrf.guard.resolve_and_validate` call returns
the resolved IP set for a URL. We then pin that set into a
:class:`~contextvars.ContextVar` for the duration of the outbound request
so the connect step uses **only** those IPs — closing the classic DNS-
rebinding TOCTOU where a malicious zone returns a public IP at validate
time and a private one at request time.

The pin lives in a ContextVar, so it survives ``await`` boundaries
inside one task and is isolated across tasks. The
:class:`PinnedHTTPTransport` reads the pin from the ContextVar at
``handle_async_request`` time, rewrites the request URL host to one of
the pinned IPs, and sets the ``Host`` header + TLS SNI back to the
original hostname so cert verification still passes.

This module imports :mod:`httpx`; importing it without the ``http`` extra
raises :class:`~resilience_kit.exceptions.MissingExtraError` at import
time.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from resilience_kit.exceptions import MissingExtraError

if TYPE_CHECKING:
    from collections.abc import Iterator

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("http", "prajwal-resilience-kit[http]") from exc

logger = logging.getLogger(__name__)

#: Per-task DNS pin. Populated by :func:`pinned`; consumed by
#: :class:`PinnedHTTPTransport`. ``None`` (the default) means "no pin in
#: effect" — the underlying transport resolves the hostname normally.
pinned_dns: ContextVar[dict[str, set[str]] | None] = ContextVar(
    "pinned_dns",
    default=None,
)


@contextmanager
def pinned(host_to_ips: dict[str, set[str]]) -> Iterator[None]:
    """Set :data:`pinned_dns` for the duration of the ``with`` block.

    The mapping is normalised — hostnames are lowercased — so callers can
    pass the URL host as-is.

    Args:
        host_to_ips: Mapping of hostname → resolved IP set. Both v4 and
            v6 addresses are accepted.

    Yields:
        Nothing — the side effect is on :data:`pinned_dns`.
    """
    normalised = {h.lower(): set(ips) for h, ips in host_to_ips.items()}
    token = pinned_dns.set(normalised)
    try:
        yield
    finally:
        pinned_dns.reset(token)


def _pick_pinned_ip(host: str) -> str | None:
    """Return one pinned IP for ``host`` (lowest-sorted), or ``None``.

    Args:
        host: Hostname to look up in :data:`pinned_dns` (case-insensitive).

    Returns:
        The first IP from the pinned set in lexical order, or ``None``
        when no pin is in effect for this host.
    """
    pins = pinned_dns.get()
    if not pins:
        return None
    ips = pins.get(host.lower())
    if not ips:
        return None
    return sorted(ips)[0]


class PinnedHTTPTransport(httpx.AsyncHTTPTransport):
    """``httpx.AsyncHTTPTransport`` that honours :data:`pinned_dns`.

    On every outbound request, if the URL host has an active pin the
    transport rewrites the request URL host to one of the pinned IPs,
    sets the ``Host`` header to the original hostname so the upstream
    routes it correctly, and writes ``sni_hostname`` into the request
    extensions so httpx's TLS handshake still sends the original
    hostname as SNI (cert verification continues to work).

    When no pin is in effect the transport behaves exactly like its
    parent.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Rewrite the request URL to a pinned IP when one is set.

        Args:
            request: The outbound request being dispatched.

        Returns:
            The response from the underlying transport.
        """
        original_host = request.url.host
        pinned_ip = _pick_pinned_ip(original_host)
        if pinned_ip is None:
            return await super().handle_async_request(request)

        # Preserve original Host header + TLS SNI so the upstream routes
        # the request correctly and cert verification still passes.
        request.headers.setdefault("Host", original_host)
        request.extensions["sni_hostname"] = original_host
        rewritten = request.url.copy_with(host=pinned_ip)
        request.url = rewritten
        logger.debug(
            "DNS pin: rewrote %s → %s for %s",
            original_host,
            pinned_ip,
            request.method,
        )
        return await super().handle_async_request(request)


__all__ = ["PinnedHTTPTransport", "pinned", "pinned_dns"]
