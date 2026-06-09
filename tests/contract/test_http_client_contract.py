"""HTTP-client contract — error-mapping uniformity across kit exceptions.

Confirms that the :func:`map_httpx_errors` ↔ kit exception mapping does
not drift between releases. Each parametrised case names the upstream
httpx error class and the kit exception it MUST land in.
"""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")

import httpx

from resilience_kit.exceptions import (
    ExternalServiceError,
    ExternalTimeoutError,
    TransientError,
)
from resilience_kit.http_client.errors import map_httpx_errors


def _exc_factory_timeout() -> Exception:
    return httpx.ConnectTimeout("slow")


def _exc_factory_read_timeout() -> Exception:
    return httpx.ReadTimeout("read slow")


def _exc_factory_dns() -> Exception:
    return httpx.ConnectError("dns boom")


def _exc_factory_4xx() -> Exception:
    req = httpx.Request("GET", "https://x.example/")
    return httpx.HTTPStatusError(
        "client error",
        request=req,
        response=httpx.Response(400, request=req),
    )


@pytest.mark.parametrize(
    ("exc_factory", "expected"),
    [
        pytest.param(_exc_factory_timeout, ExternalTimeoutError, id="connect-timeout"),
        pytest.param(_exc_factory_read_timeout, ExternalTimeoutError, id="read-timeout"),
        pytest.param(_exc_factory_dns, TransientError, id="dns-error"),
        pytest.param(_exc_factory_4xx, ExternalServiceError, id="4xx"),
    ],
)
def test_httpx_errors_land_in_locked_kit_families(
    exc_factory: object,
    expected: type[Exception],
) -> None:
    """Locked mapping: every supported httpx failure lands in the right family."""
    with (
        pytest.raises(expected),
        map_httpx_errors(url="https://x.example/", method="GET", timeout=5.0),
    ):
        raise exc_factory()  # type: ignore[operator]
