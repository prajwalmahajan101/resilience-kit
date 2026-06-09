"""Scope key derivation + rate parsing."""

from __future__ import annotations

import pytest

from resilience_kit.exceptions import ValidationError
from resilience_kit.throttle import Rate, Scope, build_key


def test_global_scope_needs_no_attrs() -> None:
    assert build_key(Scope.GLOBAL, {}) == "throttle:global"


@pytest.mark.parametrize(
    ("scope", "attrs", "expected"),
    [
        (Scope.IP, {"ip": "1.2.3.4"}, "throttle:ip:1.2.3.4"),
        (Scope.ENDPOINT, {"endpoint": "/api/v1/x"}, "throttle:endpoint:/api/v1/x"),
        (Scope.USER_TIER, {"user_tier": "gold"}, "throttle:user_tier:gold"),
        (Scope.BURST, {"ip": "1.2.3.4"}, "throttle:burst:1.2.3.4"),
        (Scope.AUTH, {"ip": "5.6.7.8"}, "throttle:auth:5.6.7.8"),
    ],
)
def test_scope_keys(scope: Scope, attrs: dict[str, str], expected: str) -> None:
    assert build_key(scope, attrs) == expected


@pytest.mark.parametrize(
    "scope",
    [Scope.IP, Scope.ENDPOINT, Scope.USER_TIER, Scope.BURST, Scope.AUTH],
)
def test_missing_required_attr_raises(scope: Scope) -> None:
    with pytest.raises(ValidationError):
        build_key(scope, {})


@pytest.mark.parametrize("spec", ["", "60", "/min", "abc/min", "60/foo", "0/min", "-1/min"])
def test_rate_parse_rejects_garbage(spec: str) -> None:
    with pytest.raises(ValidationError):
        Rate.parse(spec)
