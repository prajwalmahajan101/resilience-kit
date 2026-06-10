"""Unit tests for :mod:`resilience_kit.testing.contract`."""

from __future__ import annotations

from typing import Any

import pytest

from resilience_kit.exceptions import ResilienceKitError, ValidationError
from resilience_kit.testing import DEFAULT_KIT_EXCEPTIONS, verify_envelope_contract


def _kit_default_handler(exc: ResilienceKitError) -> dict[str, Any]:
    """Mimic the LLD §11 envelope the FastAPI/Django adapters emit."""
    return {
        "error_code": exc.error_code,
        "message": str(exc),
        "details": dict(exc.details),
    }


def _lld_envelope_schema(payload: Any) -> None:
    assert isinstance(payload, dict), f"envelope must be a dict, got {type(payload).__name__}"
    for field in ("error_code", "message", "details"):
        assert field in payload, f"envelope missing required field {field!r}"
    assert isinstance(payload["error_code"], str)
    assert isinstance(payload["message"], str)
    assert isinstance(payload["details"], dict)


def test_verify_envelope_contract_passes_for_kit_default_handler() -> None:
    # Should not raise — exercises every default kit exception.
    verify_envelope_contract(
        handler=_kit_default_handler,
        envelope_schema=_lld_envelope_schema,
    )


def test_default_kit_exceptions_covers_every_http_reachable_class() -> None:
    # Sanity: at least the nine HTTP-reachable classes (LLD §11) must be present.
    assert len(DEFAULT_KIT_EXCEPTIONS) >= 9


def test_verify_envelope_contract_reports_all_failing_exceptions() -> None:
    def broken_handler(exc: ResilienceKitError) -> dict[str, Any]:
        # Drop the required error_code field.
        return {"message": str(exc), "details": dict(exc.details)}

    with pytest.raises(AssertionError) as exc_info:
        verify_envelope_contract(
            handler=broken_handler,
            envelope_schema=_lld_envelope_schema,
        )
    message = str(exc_info.value)
    # Every default class should be named in the failure report.
    for cls in DEFAULT_KIT_EXCEPTIONS:
        assert cls.__name__ in message, f"failure report did not name {cls.__name__}"


def test_verify_envelope_contract_accepts_explicit_subset() -> None:
    verify_envelope_contract(
        handler=_kit_default_handler,
        envelope_schema=_lld_envelope_schema,
        exceptions=(ValidationError,),
    )
