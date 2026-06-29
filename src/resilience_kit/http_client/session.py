"""Pinned-DNS HTTP client factories.

Both factories install the kit's :class:`PinnedHTTPTransport` so that the
client honours :data:`resilience_kit.http_client.dns_pin.pinned_dns`. The
sync :func:`pinned_requests_session` is a thin convenience for the rare
callers that cannot use ``httpx``; new code should prefer
:func:`pinned_httpx_client`.

The factories deliberately do **not** own the client lifecycle — the
caller (or a framework adapter's lifespan) closes the client. Adapters
land in M5 (FastAPI) / M6 (Django); until then a typical pattern is::

    async with pinned_httpx_client() as client:
        ...

This module imports :mod:`httpx`; importing it without the ``http`` extra
raises :class:`~resilience_kit.exceptions.MissingExtraError` at import
time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.exceptions import MissingExtraError
from resilience_kit.http_client.dns_pin import PinnedHTTPTransport, _pick_pinned_ip

if TYPE_CHECKING:
    import requests

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("http", "resilience-kit[http]") from exc


def pinned_httpx_client(**kwargs: Any) -> httpx.AsyncClient:
    """Return an ``httpx.AsyncClient`` whose transport honours :data:`pinned_dns`.

    Redirects are forced **off** (``follow_redirects=False``). The DNS pin is
    established for the *original* request host only; httpx following a 3xx to a
    new host would resolve that host through normal DNS, never re-validated
    against SSRF and never re-pinned — so an open redirect to
    ``http://169.254.169.254/`` (cloud metadata) or an internal IP would defeat
    the pin entirely (CWE-918 + CWE-601). Callers that genuinely need redirects
    must follow them by hand, calling ``resolve_and_validate()`` on each hop's
    ``Location`` before issuing the next request.

    Args:
        **kwargs: Forwarded to :class:`httpx.AsyncClient`. A caller-
            supplied ``transport=`` overrides the default pinned
            transport (escape hatch for advanced cases — kit clients
            should never need this).

    Returns:
        A fresh :class:`httpx.AsyncClient` ready for ``async with``.

    Raises:
        ValueError: ``follow_redirects=True`` was passed. Auto-following
            redirects bypasses the DNS pin; this is refused loudly rather
            than silently overridden.
    """
    if kwargs.get("follow_redirects"):
        msg = (
            "pinned_httpx_client refuses follow_redirects=True: auto-followed "
            "redirects bypass the DNS pin (the redirect host is never "
            "re-validated against SSRF). Follow redirects manually and call "
            "resolve_and_validate() on each hop instead."
        )
        raise ValueError(msg)
    kwargs["follow_redirects"] = False
    kwargs.setdefault("transport", PinnedHTTPTransport())
    return httpx.AsyncClient(**kwargs)


def pinned_requests_session() -> requests.Session:
    """Return a ``requests.Session`` that honours :data:`pinned_dns`.

    Requires the ``requests`` extra
    (``pip install 'resilience-kit[requests]'``). The session
    mounts a transport adapter that rewrites the request URL host to one
    of the pinned IPs and sets the ``Host`` header back to the original
    hostname so the upstream routes the request correctly. TLS SNI is
    handled by ``urllib3`` via the rewritten ``Host`` header in the same
    way as the httpx transport.

    Returns:
        A fresh :class:`requests.Session`.

    Raises:
        MissingExtraError: ``requests`` is not installed.
    """
    try:
        import requests  # noqa: PLC0415
        from requests.adapters import HTTPAdapter  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise MissingExtraError(
            "requests",
            "resilience-kit[requests]",
        ) from exc

    from urllib.parse import urlparse, urlunparse  # noqa: PLC0415

    class _PinnedAdapter(HTTPAdapter):
        """``requests`` adapter that rewrites the URL host to a pinned IP."""

        def send(  # type: ignore[no-untyped-def, override]
            self,
            request,
            **kwargs: Any,
        ):
            parsed = urlparse(request.url)
            host = parsed.hostname or ""
            pinned_ip = _pick_pinned_ip(host)
            if pinned_ip is not None:
                netloc = pinned_ip
                if parsed.port is not None:
                    netloc = f"{pinned_ip}:{parsed.port}"
                request.url = urlunparse(parsed._replace(netloc=netloc))
                request.headers.setdefault("Host", host)
            return super().send(request, **kwargs)

    session = requests.Session()
    adapter = _PinnedAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


__all__ = ["pinned_httpx_client", "pinned_requests_session"]
