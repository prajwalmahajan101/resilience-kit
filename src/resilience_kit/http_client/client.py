"""``AsyncAPIClient`` — outbound HTTP with full kit protection (LLD §5).

The class composes the M3 building blocks into a single callable shape::

    ssrf.resolve_and_validate(url) → ssrf.assert_allowed_url(url)
        → dns_pin.pinned(host → ips) → @resilient(service) [breaker ∘ retry]
        → httpx.AsyncClient.request → audit-hook callback

One outbound call, one decorator, one place to forget nothing.

The sync mirror :meth:`AsyncAPIClient.request_sync` exists for legacy
callers — it drives a **private** event loop only when no loop is
running; calling it from inside a running loop is a programmer error
and raises :class:`RuntimeError` immediately.

Audit-subsystem wiring lands in M4. Until then this module accepts an
optional ``on_outbound`` callable per client that receives the
:class:`OutboundCall` record after every request (success or failure).

This module imports :mod:`httpx`; importing it without the ``http``
extra raises :class:`~resilience_kit.exceptions.MissingExtraError` at
import time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from resilience_kit.decorators import resilient
from resilience_kit.exceptions import MissingExtraError
from resilience_kit.http_client.dns_pin import pinned
from resilience_kit.http_client.errors import map_httpx_errors, raise_for_server_error
from resilience_kit.http_client.session import pinned_httpx_client
from resilience_kit.ssrf import assert_allowed_url, resolve_and_validate

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

try:
    import httpx  # noqa: TC002 — runtime use (httpx.AsyncClient, httpx.Response, httpx.Auth).
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("http", "prajwal-resilience-kit[http]") from exc

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT: float = 30.0


@dataclass(slots=True)
class OutboundCall:
    """Audit-shaped record published after every outbound request.

    M4 wires this into the audit pipeline (sanitiser + dispatcher + sink).
    In M3 it is delivered only to the optional ``on_outbound`` callable.
    """

    service: str
    method: str
    url: str
    status: int | None
    latency_ms: float
    error_class: str | None = None
    error_code: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


class AsyncAPIClient:
    """Outbound HTTP client wired with SSRF + DNS-pin + breaker + retry + audit.

    The ``service`` argument names the per-service config in
    :data:`resilience_kit.registry.registry`; the breaker + retry policy
    is read from there at decorate time.
    """

    def __init__(
        self,
        service: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
        on_outbound: Callable[[OutboundCall], None] | None = None,
        check_ssrf: bool = True,
    ) -> None:
        """Initialise the client.

        Args:
            service: Service name registered (or auto-defaulted) in
                :data:`~resilience_kit.registry.registry`. Drives the
                breaker / retry policy via :func:`resilient`.
            timeout: Per-request timeout in seconds.
            client: Optional pre-built :class:`httpx.AsyncClient` —
                useful when an adapter owns the client lifecycle. When
                ``None``, the request method allocates a fresh
                :func:`pinned_httpx_client` per call.
            on_outbound: Optional callable invoked with an
                :class:`OutboundCall` after every request. Errors raised
                from the callable are logged and swallowed so they do
                not affect the caller.
            check_ssrf: When ``False``, skip private-IP rejection (used
                only by tests pointing at localhost mocks). The
                allow-list still runs.
        """
        self.service = service
        self.timeout = timeout
        self._client = client
        self._on_outbound = on_outbound
        self._check_ssrf = check_ssrf
        # @resilient(service) wraps the inner call so breaker + retry
        # are applied uniformly. Composing once at __init__ keeps the
        # decorator registry lookup off the hot path.
        self._send = resilient(service)(self._raw_send)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        content: bytes | str | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.Response:
        """Issue a single HTTP request with full kit protection.

        Args:
            method: HTTP verb (``GET`` / ``POST`` / …).
            url: Absolute target URL.
            params: Query-string parameters.
            headers: Caller-supplied headers (merged with defaults).
            json: JSON body — mutually exclusive with ``data`` /
                ``content`` per ``httpx``'s rules.
            data: Form-encoded body.
            content: Raw bytes / string body.
            auth: Optional :class:`httpx.Auth` for this call —
                typically a :class:`~resilience_kit.http_client.auth.BearerAuth`
                or :class:`~resilience_kit.http_client.auth.HMACAuth`.

        Returns:
            The :class:`httpx.Response`. Successful responses pass
            through; 5xx is converted to :class:`ExternalTimeoutError`
            before return so the breaker counts the failure and
            ``@retry`` retries.

        Raises:
            ValidationError: SSRF / allow-list rejection.
            ExternalTimeoutError: Timeout or 5xx.
            ExternalServiceError: 4xx response.
            TransientError: Transport-level error (DNS / SSL / reset).
        """
        # 1. SSRF: validate scheme + resolve hostname + reject private IPs.
        #    Returns the resolved IP set so we can pin it across connect.
        resolved_ips = resolve_and_validate(url) if self._check_ssrf else set()
        # 2. Allow-list check (defence-in-depth).
        assert_allowed_url(url)

        host = (urlparse(url).hostname or "").lower()
        call_kwargs = {
            "method": method,
            "url": url,
            "params": params,
            "headers": headers,
            "json": json,
            "data": data,
            "content": content,
            "auth": auth,
            "host": host,
            "resolved_ips": resolved_ips,
        }
        # 3. Pin DNS for the duration of the call, then dispatch through
        #    the @resilient(service) wrapper so the breaker sees the call
        #    boundary even when the inner httpx request raises.
        pin_map: dict[str, set[str]] = {host: resolved_ips} if resolved_ips and host else {}
        if pin_map:
            with pinned(pin_map):
                return await self._send(**call_kwargs)
        return await self._send(**call_kwargs)

    async def _raw_send(
        self,
        *,
        method: str,
        url: str,
        host: str,
        resolved_ips: set[str],
        params: Mapping[str, Any] | None,
        headers: Mapping[str, str] | None,
        json: Any,
        data: Any,
        content: bytes | str | None,
        auth: httpx.Auth | None,
    ) -> httpx.Response:
        """Inner call wrapped by ``@resilient(service)`` — actual HTTP dispatch.

        Args:
            method: HTTP verb.
            url: Absolute target URL.
            host: Lower-cased hostname — kept on the call for audit logs.
            resolved_ips: The pinned IP set — kept for audit logs.
            params: Query-string parameters.
            headers: Caller-supplied headers.
            json: JSON body.
            data: Form-encoded body.
            content: Raw body.
            auth: Optional per-call :class:`httpx.Auth`.

        Returns:
            The successful :class:`httpx.Response`.
        """
        started = time.monotonic()
        response: httpx.Response | None = None
        error_class: str | None = None
        error_code: str | None = None
        try:
            client_cm = (
                _NullCloseClient(self._client)
                if self._client is not None
                else pinned_httpx_client(timeout=self.timeout)
            )
            async with client_cm as client:
                with map_httpx_errors(url=url, method=method, timeout=self.timeout):
                    response = await client.request(
                        method,
                        url,
                        params=params,
                        headers=dict(headers) if headers else None,
                        json=json,
                        data=data,
                        content=content,
                        auth=auth,
                    )
            raise_for_server_error(url, response.status_code)
        except Exception as exc:
            error_class = type(exc).__name__
            error_code = getattr(exc, "error_code", None)
            raise
        finally:
            latency_ms = (time.monotonic() - started) * 1000
            self._emit_audit(
                OutboundCall(
                    service=self.service,
                    method=method,
                    url=url,
                    status=response.status_code if response is not None else None,
                    latency_ms=latency_ms,
                    error_class=error_class,
                    error_code=error_code,
                    details={"host": host},
                ),
            )
        return response

    def _emit_audit(self, call: OutboundCall) -> None:
        """Hand ``call`` to the configured audit sink.

        Precedence:

        1. The caller-supplied ``on_outbound`` callback, if any.
        2. Otherwise, the kit's audit dispatcher
           (:func:`resilience_kit.audit.get_dispatcher`) receives an
           :class:`~resilience_kit.audit.AuditEvent` built from the
           call. The dispatcher is lazy-built from settings so callers
           who never configure audit see the kit default (noop).

        Errors anywhere in this method are logged and swallowed — the
        observability path can never fail the request.

        Args:
            call: The audit record.
        """
        if self._on_outbound is not None:
            try:
                self._on_outbound(call)
            except Exception:
                logger.exception("on_outbound callback raised; suppressing.")
            return
        try:
            self._submit_to_dispatcher(call)
        except Exception:
            logger.exception("audit dispatch raised; suppressing.")

    @staticmethod
    def _submit_to_dispatcher(call: OutboundCall) -> None:
        """Translate :class:`OutboundCall` → :class:`AuditEvent` and dispatch."""
        from resilience_kit.audit import AuditEvent, get_dispatcher  # noqa: PLC0415
        from resilience_kit.context import (  # noqa: PLC0415
            correlation_id,
            request_id,
        )

        event = AuditEvent(
            direction="outbound",
            service=call.service,
            method=call.method,
            path=call.url,
            outcome="failure" if call.error_class else "success",
            latency_ms=call.latency_ms,
            status=call.status,
            error_class=call.error_class,
            error_code=call.error_code,
            request_id=request_id.get(),
            correlation_id=correlation_id.get(),
            details=call.details,
        )
        get_dispatcher().submit(event)

    # ── Verb shortcuts ────────────────────────────────────────────────

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Issue a ``GET`` request."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Issue a ``POST`` request."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Issue a ``PUT`` request."""
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Issue a ``PATCH`` request."""
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Issue a ``DELETE`` request."""
        return await self.request("DELETE", url, **kwargs)

    # ── Sync mirror ───────────────────────────────────────────────────

    def request_sync(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Synchronous mirror — drives a private loop when no loop runs.

        Args:
            method: HTTP verb.
            url: Absolute target URL.
            **kwargs: Forwarded to :meth:`request`.

        Returns:
            The same :class:`httpx.Response` as :meth:`request`.

        Raises:
            RuntimeError: Called from inside a running event loop —
                the caller must use :meth:`request` instead. Nesting
                ``asyncio.run`` is never the right answer.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.request(method, url, **kwargs))
        msg = (
            "AsyncAPIClient.request_sync called from a running event loop; "
            "use the async `request` method instead."
        )
        raise RuntimeError(msg)


class _NullCloseClient:
    """Async-context wrapper that yields the client without closing it.

    Used when the caller supplied a pre-built :class:`httpx.AsyncClient`
    — its lifecycle belongs to the caller / adapter, not to the
    individual request.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        """Wrap ``client``."""
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        """Return the underlying client."""
        return self._client

    async def __aexit__(self, *_exc: object) -> None:
        """Do not close — caller owns the lifecycle."""
        return


__all__ = ["AsyncAPIClient", "OutboundCall"]
