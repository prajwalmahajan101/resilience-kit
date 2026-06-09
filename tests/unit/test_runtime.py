"""Runtime indirection: settings caching + source swap."""

from __future__ import annotations

import pytest

from resilience_kit.exceptions import ValidationError
from resilience_kit.runtime import get_settings, require, reset_settings_cache, set_settings_source
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
