"""Exceptions carry stable error_code + structured details."""

from __future__ import annotations

import pytest

from resilience_kit.exceptions import (
    DecryptionError,
    ExternalServiceError,
    ExternalTimeoutError,
    MissingExtraError,
    RateLimitError,
    RepositoryError,
    ResilienceKitError,
    ServiceUnavailableError,
    TransientError,
    UnknownBackendError,
    ValidationError,
)


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        (TransientError, "TRANSIENT_ERROR"),
        (ExternalTimeoutError, "EXTERNAL_TIMEOUT"),
        (ExternalServiceError, "EXTERNAL_SERVICE_ERROR"),
        (RepositoryError, "REPOSITORY_ERROR"),
        (DecryptionError, "DECRYPTION_ERROR"),
        (ValidationError, "VALIDATION_ERROR"),
    ],
)
def test_simple_exceptions_carry_code(cls: type[ResilienceKitError], code: str) -> None:
    exc = cls("oops")
    assert exc.error_code == code
    assert "oops" in str(exc)


def test_service_unavailable_carries_service_name() -> None:
    exc = ServiceUnavailableError("payments")
    assert exc.service_name == "payments"
    assert exc.error_code == "SERVICE_UNAVAILABLE"
    assert exc.details["service_name"] == "payments"


def test_rate_limit_response_headers() -> None:
    exc = RateLimitError(limit=60, remaining=0, reset_at=1_700_000_060, retry_after=12.5)
    headers = exc.response_headers()
    assert headers["X-RateLimit-Limit"] == "60"
    assert headers["X-RateLimit-Remaining"] == "0"
    assert headers["X-RateLimit-Reset"] == "1700000060"
    # Retry-After is rounded up.
    assert headers["Retry-After"] == "13"


def test_missing_extra_carries_install_hint() -> None:
    exc = MissingExtraError(extra="redis", install_hint="prajwal-resilience-kit[redis]")
    assert exc.extra == "redis"
    assert "prajwal-resilience-kit[redis]" in str(exc)


def test_unknown_backend_lists_options() -> None:
    exc = UnknownBackendError(
        group="resilience_kit.cache_backends",
        name="memcached",
        available=["memory", "redis"],
    )
    assert "memcached" in str(exc)
    assert exc.available == ("memory", "redis")


def test_with_details_chains() -> None:
    exc = TransientError("oops").with_details(retry_after=5)
    assert exc.details["retry_after"] == 5
