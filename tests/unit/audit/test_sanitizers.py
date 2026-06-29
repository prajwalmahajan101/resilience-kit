"""Unit tests for :mod:`resilience_kit.audit.sanitizers`."""

from __future__ import annotations

import pytest

from resilience_kit.audit.sanitizers import (
    GLOBAL_PII_PATTERNS,
    REDACTED,
    DefaultRedactor,
    IndiaFintechRedactor,
    RegexRedactor,
    Sanitizer,
)


def test_default_redactor_satisfies_protocol() -> None:
    """The default redactor satisfies the Sanitizer protocol at runtime."""
    assert isinstance(DefaultRedactor(), Sanitizer)


def test_redacts_top_level_fields() -> None:
    """Configured key fragments are redacted (substring + case-insensitive)."""
    out = DefaultRedactor().sanitize(
        {"username": "alice", "password": "p@ss", "API_KEY": "k"},
    )
    assert out["username"] == "alice"
    assert out["password"] == REDACTED
    assert out["API_KEY"] == REDACTED


def test_substring_matching() -> None:
    """A key containing a fragment also redacts (e.g. ``user_password``)."""
    out = DefaultRedactor().sanitize({"user_password": "x", "user_name": "alice"})
    assert out["user_password"] == REDACTED
    assert out["user_name"] == "alice"


def test_redacts_cookie_headers_by_default() -> None:
    """Cookie and Set-Cookie are redacted by default, case-insensitively (#A1)."""
    out = DefaultRedactor().sanitize(
        {
            "headers": {
                "Cookie": "session=abc123",
                "SET-COOKIE": "session=def456; HttpOnly",
                "Accept": "application/json",
            },
        },
    )
    assert out["headers"]["Cookie"] == REDACTED
    assert out["headers"]["SET-COOKIE"] == REDACTED
    assert out["headers"]["Accept"] == "application/json"


def test_deep_walks_dicts_and_lists() -> None:
    """Nested dicts and lists are walked; sensitive values inside are redacted."""
    src = {
        "outer": {
            "inner": {"token": "abc", "ok": "fine"},
            "items": [{"secret": "x"}, {"value": 1}],
        },
        "headers": {"Authorization": "Bearer abc"},
    }
    out = DefaultRedactor().sanitize(src)
    assert out["outer"]["inner"]["token"] == REDACTED
    assert out["outer"]["inner"]["ok"] == "fine"
    assert out["outer"]["items"][0]["secret"] == REDACTED
    assert out["outer"]["items"][1]["value"] == 1
    assert out["headers"]["Authorization"] == REDACTED


def test_source_is_not_mutated() -> None:
    """The redactor returns a copy; the original payload is untouched."""
    src = {"password": "x", "ok": "fine"}
    out = DefaultRedactor().sanitize(src)
    assert src["password"] == "x"
    assert out["password"] == REDACTED


def test_custom_fields_replace_defaults() -> None:
    """Constructor argument replaces the default fragment set."""
    out = DefaultRedactor(fields=["pin"]).sanitize(
        {"pin": "1234", "password": "leave-me"},
    )
    assert out["pin"] == REDACTED
    # 'password' is no longer in the redact set.
    assert out["password"] == "leave-me"


@pytest.mark.parametrize(
    "value",
    [42, "plain", None, [1, 2, 3], (1, 2)],
)
def test_non_redacted_values_pass_through(value: object) -> None:
    """Non-mapping leaves untouched."""
    out = DefaultRedactor().sanitize({"k": value})
    assert out["k"] == value


# --- #C5: value-scanning redactors -------------------------------------


def test_india_redactor_satisfies_protocol() -> None:
    """The fintech redactor satisfies the Sanitizer protocol at runtime."""
    assert isinstance(IndiaFintechRedactor(), Sanitizer)


def test_pan_in_free_text_value_is_masked() -> None:
    """A PAN embedded in an innocuous field value is scrubbed (#C5 acceptance)."""
    out = IndiaFintechRedactor().sanitize({"notes": "customer PAN ABCDE1234F here"})
    assert out["notes"] == f"customer PAN {REDACTED} here"


def test_india_identifiers_in_values_are_masked() -> None:
    """IFSC, Aadhaar, and Indian mobile numbers are scrubbed inside values."""
    out = IndiaFintechRedactor().sanitize(
        {
            "ifsc": "branch HDFC0001234",
            "uid": "id 1234 5678 9012",
            "phone": "call +919812345678 now",
        },
    )
    assert out["ifsc"] == f"branch {REDACTED}"
    assert out["uid"] == f"id {REDACTED}"
    assert out["phone"] == f"call {REDACTED} now"


def test_email_in_value_is_masked() -> None:
    """Global pack scrubs an email embedded in a value."""
    out = IndiaFintechRedactor().sanitize({"msg": "reach me at alice@example.com ok"})
    assert out["msg"] == f"reach me at {REDACTED} ok"


def test_luhn_valid_card_masked_invalid_left_alone() -> None:
    """Card pattern masks Luhn-valid numbers only (no broad bank-account rule)."""
    redactor = RegexRedactor(patterns=GLOBAL_PII_PATTERNS)
    out = redactor.sanitize(
        {"valid": "card 4111111111111111", "invalid": "ref 4111111111111112"},
    )
    assert out["valid"] == f"card {REDACTED}"
    # Luhn-invalid 16-digit run is not a plausible card and is left intact.
    assert out["invalid"] == "ref 4111111111111112"


def test_field_name_redaction_still_applies() -> None:
    """The regex redactor inherits DefaultRedactor key-name matching."""
    out = IndiaFintechRedactor().sanitize({"password": "p@ss", "ok": "fine"})
    assert out["password"] == REDACTED
    assert out["ok"] == "fine"


def test_value_scanning_walks_nested_structures() -> None:
    """PII inside nested dicts and lists is scrubbed."""
    out = IndiaFintechRedactor().sanitize(
        {"outer": {"items": ["PAN ABCDE1234F", "clean text"]}},
    )
    assert out["outer"]["items"][0] == f"PAN {REDACTED}"
    assert out["outer"]["items"][1] == "clean text"


def test_regex_redactor_does_not_mutate_source() -> None:
    """Value-scanning returns a copy; the original payload is untouched."""
    src = {"notes": "PAN ABCDE1234F"}
    out = IndiaFintechRedactor().sanitize(src)
    assert src["notes"] == "PAN ABCDE1234F"
    assert out["notes"] == f"PAN {REDACTED}"


def test_india_redactor_accepts_fields_kwarg() -> None:
    """Factory compatibility: resolved with ``fields=`` like every sanitiser."""
    redactor = IndiaFintechRedactor(fields=["pin"])
    out = redactor.sanitize({"pin": "1234", "notes": "PAN ABCDE1234F"})
    assert out["pin"] == REDACTED
    assert out["notes"] == f"PAN {REDACTED}"
