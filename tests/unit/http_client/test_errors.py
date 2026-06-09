"""Unit tests for :mod:`resilience_kit.http_client.errors`."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")

import httpx

from resilience_kit.exceptions import (
    ExternalServiceError,
    ExternalTimeoutError,
    TransientError,
)
from resilience_kit.http_client.errors import (
    map_httpx_errors,
    raise_for_server_error,
)

# --- raise_for_server_error -------------------------------------------------


@pytest.mark.parametrize("status", [500, 502, 503, 599])
def test_raise_for_server_error_5xx(status: int) -> None:
    """5xx is mapped onto the transient family."""
    with pytest.raises(ExternalTimeoutError):
        raise_for_server_error("https://partner.example/", status)


@pytest.mark.parametrize("status", [200, 301, 400, 404, 499])
def test_raise_for_server_error_non_5xx_passes(status: int) -> None:
    """4xx and successes do not raise here — 4xx is handled by httpx.raise_for_status."""
    raise_for_server_error("https://partner.example/", status)


# --- map_httpx_errors -------------------------------------------------------


def test_map_timeout_to_external_timeout() -> None:
    """``httpx.TimeoutException`` becomes ``ExternalTimeoutError``."""
    with (
        pytest.raises(ExternalTimeoutError, match="timed out"),
        map_httpx_errors(url="https://x.example/", method="GET", timeout=5.0),
    ):
        raise httpx.ConnectTimeout("slow")


def test_map_4xx_to_external_service_error() -> None:
    """``httpx.HTTPStatusError`` (4xx) becomes ``ExternalServiceError``."""
    req = httpx.Request("GET", "https://x.example/")
    resp = httpx.Response(404, request=req)
    with (
        pytest.raises(ExternalServiceError, match="HTTP 404"),
        map_httpx_errors(url="https://x.example/", method="GET", timeout=5.0),
    ):
        raise httpx.HTTPStatusError("404", request=req, response=resp)


def test_map_request_error_to_transient() -> None:
    """Any other ``httpx.RequestError`` becomes ``TransientError``."""
    with (
        pytest.raises(TransientError, match="Transport error"),
        map_httpx_errors(url="https://x.example/", method="GET", timeout=5.0),
    ):
        raise httpx.ConnectError("dns boom")


def test_success_passes_through() -> None:
    """No exception → context manager is a no-op."""
    with map_httpx_errors(url="https://x.example/", method="GET", timeout=5.0):
        pass
