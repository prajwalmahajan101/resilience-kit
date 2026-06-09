"""Unit tests for :mod:`resilience_kit.audit.sanitizers`."""

from __future__ import annotations

import pytest

from resilience_kit.audit.sanitizers import REDACTED, DefaultRedactor, Sanitizer


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
