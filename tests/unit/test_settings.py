"""Strictness tests for :class:`ResilienceSettings`.

Locks in ``extra="forbid"`` at the root: unknown top-level keys (env vars
or dicts) must raise ``ValidationError`` rather than silently dropping.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from resilience_kit.settings import ResilienceSettings


def test_unknown_top_level_key_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ResilienceSettings.model_validate(
            {"backend": "memory", "some_future_field": "oops"}
        )
    assert "some_future_field" in str(exc_info.value)


def test_typo_in_nested_key_path_raises() -> None:
    # The user *meant* `defaults.retry.max_attempts` but typo'd at the root.
    # extra="forbid" catches the misspelled top-level key.
    with pytest.raises(ValidationError) as exc_info:
        ResilienceSettings.model_validate(
            {"deafults": {"retry": {"max_attempts": 10}}}
        )
    assert "deafults" in str(exc_info.value)


def test_django_settings_dict_typo_raises() -> None:
    # The Django adapter loads from settings.RESILIENCE = {...}; that's
    # the path that benefits most from extra="forbid".
    with pytest.raises(ValidationError) as exc_info:
        ResilienceSettings.model_validate(
            {
                "backend": "redis",
                "CIRCUIT_BREAKER_CONFIG": {"fail_max": 5},  # legacy key
            }
        )
    assert "CIRCUIT_BREAKER_CONFIG" in str(exc_info.value)


def test_known_keys_still_load() -> None:
    settings = ResilienceSettings.model_validate({"backend": "memory"})
    assert settings.backend == "memory"


def test_known_nested_dict_still_loads() -> None:
    settings = ResilienceSettings.model_validate(
        {"defaults": {"retry": {"max_attempts": 7}}}
    )
    assert settings.defaults.retry.max_attempts == 7
