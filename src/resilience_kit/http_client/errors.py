"""Map ``httpx`` failures onto the kit's typed exception families.

Extracted from :class:`~resilience_kit.http_client.AsyncAPIClient` so the
mapping is unit-testable in isolation: a 5xx response, a transport
hiccup, and a timeout each need to land in a specific typed family so the
``@resilient`` decorator can decide whether to retry.

Mapping (locked at v0.1 per LLD §11):

* :class:`httpx.TimeoutException` → :class:`~resilience_kit.exceptions.ExternalTimeoutError`
  (transient; retried by ``@retry``)
* HTTP status ``>= 500`` → :class:`~resilience_kit.exceptions.ExternalTimeoutError`
  via :func:`raise_for_server_error` — counted as transient so the
  breaker sees the failure and ``@retry`` will retry once
* HTTP status ``4xx`` (via :class:`httpx.HTTPStatusError`) →
  :class:`~resilience_kit.exceptions.ExternalServiceError` (not retried;
  the breaker counts it as a failure)
* Any other :class:`httpx.RequestError` (DNS, SSL, connection reset) →
  :class:`~resilience_kit.exceptions.TransientError`

This module imports :mod:`httpx`; importing it without the ``http`` extra
raises :class:`~resilience_kit.exceptions.MissingExtraError` at import
time so the failure is immediate.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from resilience_kit.exceptions import (
    ExternalServiceError,
    ExternalTimeoutError,
    MissingExtraError,
    TransientError,
)
from resilience_kit.ssrf import safe_host

if TYPE_CHECKING:
    from collections.abc import Iterator

try:
    import httpx
except ImportError as exc:  # pragma: no cover - exercised by missing_extra test
    raise MissingExtraError("http", "prajwal-resilience-kit[http]") from exc

logger = logging.getLogger(__name__)


def raise_for_server_error(url: str, status: int) -> None:
    """Raise :class:`ExternalTimeoutError` when ``status`` is a 5xx response.

    5xx is mapped onto the transient family so ``@retry`` retries it and
    the breaker counts the failure. 4xx is **not** transient and is
    handled by :func:`map_httpx_errors` from the
    :class:`httpx.HTTPStatusError` raised by ``response.raise_for_status()``.

    Args:
        url: Target URL — only the host appears in the message.
        status: HTTP status code returned by the upstream.

    Raises:
        ExternalTimeoutError: When ``status >= 500``.
    """
    if status >= 500:
        raise ExternalTimeoutError(
            f"Server error from {safe_host(url)}: HTTP {status}",
            details={"host": safe_host(url), "status": status},
        )


@contextmanager
def map_httpx_errors(*, url: str, method: str, timeout: float) -> Iterator[None]:
    """Translate ``httpx`` failures into typed kit exceptions.

    Wraps the caller's ``await client.request(...)`` block. Success
    passes through unchanged; any failure is logged with request context
    and re-raised as the matching typed family.

    Args:
        url: Absolute target URL — used for messages and structured logs.
        method: HTTP verb — for structured logs.
        timeout: Request timeout in seconds — embedded in the timeout
            message so observability can correlate to the budget set on
            the call.

    Yields:
        Nothing — wraps the caller's request block.

    Raises:
        ExternalTimeoutError: The upstream timed out.
        ExternalServiceError: The upstream returned a 4xx response.
        TransientError: ``httpx`` raised a transport-level error
            (DNS / SSL / connection reset / etc.).
    """
    try:
        yield
    except httpx.TimeoutException as exc:
        logger.error(
            "HTTP request timeout",
            extra={"url": url, "method": method, "timeout": timeout},
        )
        raise ExternalTimeoutError(
            f"Request to {safe_host(url)} timed out after {timeout}s",
            details={"host": safe_host(url), "timeout": timeout, "method": method},
        ) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        logger.error(
            "HTTP non-success response",
            extra={"url": url, "method": method, "status": status},
        )
        raise ExternalServiceError(
            f"HTTP {status} from {safe_host(url)}",
            details={
                "host": safe_host(url),
                "status": status,
                "method": method,
            },
        ) from exc
    except httpx.RequestError as exc:
        logger.error(
            "HTTP transport error",
            extra={
                "url": url,
                "method": method,
                "error_class": type(exc).__name__,
            },
        )
        raise TransientError(
            f"Transport error contacting {safe_host(url)}: {type(exc).__name__}",
            details={"host": safe_host(url), "method": method},
        ) from exc


__all__ = ["map_httpx_errors", "raise_for_server_error"]
