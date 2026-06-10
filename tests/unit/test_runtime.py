"""Runtime indirection: settings caching + source swap."""

from __future__ import annotations

import pytest

from resilience_kit.exceptions import ValidationError
from resilience_kit.runtime import (
    DEFAULT_ALIASES,
    get_settings,
    legacy_env_alias,
    require,
    reset_settings_cache,
    set_settings_source,
)
from resilience_kit.settings import ResilienceSettings


def test_get_settings_returns_cached_instance() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b


def test_reset_clears_cache() -> None:
    a = get_settings()
    reset_settings_cache()
    b = get_settings()
    assert a is not b


def test_custom_source_takes_effect() -> None:
    custom = ResilienceSettings(backend="memory")

    class FixedSource:
        def load(self) -> ResilienceSettings:
            return custom

    set_settings_source(FixedSource())
    assert get_settings() is custom


def test_require_passes_through_truthy() -> None:
    assert require("hello", name="api_key") == "hello"


@pytest.mark.parametrize("falsy", ["", None, 0, [], {}])
def test_require_raises_on_falsy(falsy: object) -> None:
    with pytest.raises(ValidationError, match="api_key"):
        require(falsy, name="api_key")


def test_legacy_env_alias_copies_value_to_kit_name() -> None:
    env: dict[str, str] = {"FIELD_ENCRYPTION_KEY": "secret-token"}
    applied = legacy_env_alias(env=env, warn=False)
    assert env["RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY"] == "secret-token"
    assert applied["FIELD_ENCRYPTION_KEY"] == "RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY"


def test_legacy_env_alias_does_not_overwrite_new_name() -> None:
    env: dict[str, str] = {
        "FIELD_ENCRYPTION_KEY": "legacy-value",
        "RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY": "kit-value",
    }
    legacy_env_alias(env=env, warn=False)
    # New name preserved unchanged.
    assert env["RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY"] == "kit-value"


def test_legacy_env_alias_emits_deprecation_warning() -> None:
    env: dict[str, str] = {"FIELD_ENCRYPTION_KEY": "v"}
    with pytest.warns(DeprecationWarning, match="FIELD_ENCRYPTION_KEY"):
        legacy_env_alias(env=env)


def test_legacy_env_alias_warns_on_collision() -> None:
    env: dict[str, str] = {
        "RATE_LIMIT_AUTH": "legacy",
        "RESILIENCE_DEFAULTS__THROTTLE__AUTH_RATE": "kit",
    }
    with pytest.warns(DeprecationWarning, match="kit will use"):
        legacy_env_alias(env=env)


def test_legacy_env_alias_returns_only_translated_pairs() -> None:
    env: dict[str, str] = {
        "FIELD_ENCRYPTION_KEY": "v",
        "UNRELATED_VAR": "x",
    }
    applied = legacy_env_alias(env=env, warn=False)
    assert "FIELD_ENCRYPTION_KEY" in applied
    assert "UNRELATED_VAR" not in applied


def test_default_aliases_covers_migration_section_10_5() -> None:
    # Sanity: every entry the migration doc promised is in the table.
    expected_keys = {
        "FIELD_ENCRYPTION_KEY",
        "REDIS_URL",
        "OUTBOUND_ALLOWLIST",
        "RATE_LIMIT_ANON",
        "RATE_LIMIT_AUTH",
        "RATE_LIMIT_BURST",
        "CIRCUIT_BREAKER_FAIL_MAX",
        "CIRCUIT_BREAKER_RESET_TIMEOUT",
        "RECOVERY_PROBE_INTERVAL",
        "AUDIT_SINK",
    }
    assert expected_keys <= set(DEFAULT_ALIASES.keys())
