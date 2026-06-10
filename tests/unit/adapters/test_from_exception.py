"""Unit tests for :func:`resilience_kit.adapters._envelope.from_exception`."""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from pydantic import BaseModel

from resilience_kit.adapters._envelope import from_exception
from resilience_kit.context import bind
from resilience_kit.exceptions import (
    DecryptionError,
    ExternalServiceError,
    ExternalTimeoutError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)


def test_default_envelope_shape_matches_lld_section_11() -> None:
    body, status, headers = from_exception(ValidationError("bad input", details={"field": "x"}))
    assert body == {
        "error_code": "VALIDATION_ERROR",
        "message": "bad input",
        "details": {"field": "x"},
    }
    assert status == 400
    assert headers == {}


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (ValidationError("v"), 400),
        (ServiceUnavailableError("svc"), 503),
        (ExternalTimeoutError("t"), 504),
        (ExternalServiceError("e"), 502),
        (DecryptionError("d"), 500),
    ],
)
def test_status_via_http_status_for(exc: Exception, expected_status: int) -> None:
    _, status, _ = from_exception(exc)  # type: ignore[arg-type]
    assert status == expected_status


def test_rate_limit_adds_retry_after_and_xratelimit_headers() -> None:
    exc = RateLimitError(limit=60, remaining=0, reset_at=1700000000, retry_after=12.5)
    body, status, headers = from_exception(exc)
    assert status == 429
    assert headers["Retry-After"] == "13"
    assert headers["X-RateLimit-Limit"] == "60"
    assert headers["X-RateLimit-Remaining"] == "0"
    assert headers["X-RateLimit-Reset"] == "1700000000"
    # Body remains LLD shape.
    assert body["error_code"] == "RATE_LIMIT_EXCEEDED"


def test_extra_headers_merge_under_rate_limit_headers() -> None:
    exc = RateLimitError(limit=1, remaining=0, reset_at=0, retry_after=1.0)
    _, _, headers = from_exception(exc, extra_headers={"X-Trace": "abc", "Retry-After": "999"})
    assert headers["X-Trace"] == "abc"
    # Rate-limit's authoritative Retry-After overrides any caller supplied one.
    assert headers["Retry-After"] != "999"


class _BoilerplateEnvelope(BaseModel):
    success: bool
    message: str
    errors: list[dict[str, str]]
    request_id: str | None = None


def test_envelope_cls_projects_field_names_with_errors_list_shape() -> None:
    exc = ValidationError("bad", details={"field": "x", "row": "7"})
    with bind(request_id_value="req-123"):
        body, _, _ = from_exception(exc, envelope_cls=_BoilerplateEnvelope)
    assert body["success"] is False
    assert body["message"] == "bad"
    assert body["errors"] == [
        {"field": "field", "message": "x"},
        {"field": "field", "message": "7"},
    ] or body["errors"] == [
        {"field": "field", "message": "x"},
        {"field": "row", "message": "7"},
    ]
    # Tighten: details keys preserved exactly.
    fields_in_errors = [item["field"] for item in body["errors"]]
    assert fields_in_errors == ["field", "row"]
    assert body["request_id"] == "req-123"


class _AlternateEnvelope(BaseModel):
    code: str
    detail: str
    details: dict[str, str]


def test_envelope_cls_uses_code_and_detail_aliases() -> None:
    body, _, _ = from_exception(
        ValidationError("oops", details={"k": "v"}),
        envelope_cls=_AlternateEnvelope,
    )
    assert body == {"code": "VALIDATION_ERROR", "detail": "oops", "details": {"k": "v"}}


class _NoRequestIdEnvelope(BaseModel):
    error_code: str
    message: str
    details: dict[str, str]


def test_envelope_cls_omits_request_id_when_field_absent() -> None:
    body, _, _ = from_exception(
        ValidationError("oops", details={"k": "v"}),
        envelope_cls=_NoRequestIdEnvelope,
    )
    assert "request_id" not in body
    assert "success" not in body
