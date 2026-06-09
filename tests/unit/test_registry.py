"""Per-service config merge + breaker caching."""

from __future__ import annotations

import pytest

from resilience_kit.exceptions import TransientError
from resilience_kit.registry import ResilienceRegistry


def test_defaults_apply_when_no_overrides() -> None:
    r = ResilienceRegistry()
    cfg = r.get_config("svc")
    assert cfg.retry.max_attempts == 3
    assert cfg.circuit_breaker.fail_max == 5
    assert cfg.retry.retry_on == (TransientError,)


def test_overrides_win_field_by_field() -> None:
    r = ResilienceRegistry()
    r.register_service(
        "svc",
        {"retry": {"max_attempts": 7}, "circuit_breaker": {"fail_max": 9}},
    )
    cfg = r.get_config("svc")
    assert cfg.retry.max_attempts == 7
    assert cfg.circuit_breaker.fail_max == 9
    # Unspecified fields still default.
    assert cfg.retry.wait_min == 1.0


def test_get_breaker_returns_same_instance_per_name() -> None:
    r = ResilienceRegistry()
    a = r.get_breaker("svc")
    b = r.get_breaker("svc")
    assert a is b


def test_register_service_invalidates_cached_breaker() -> None:
    r = ResilienceRegistry()
    a = r.get_breaker("svc")
    r.register_service("svc", {"circuit_breaker": {"fail_max": 99}})
    b = r.get_breaker("svc")
    assert a is not b
    assert b.config.fail_max == 99


def test_retry_on_rejects_non_exception_classes() -> None:
    r = ResilienceRegistry()
    r.register_service("svc", {"retry": {"retry_on": (str,)}})
    with pytest.raises(TypeError):
        r.get_config("svc")


def test_reset_clears_state() -> None:
    r = ResilienceRegistry()
    r.register_service("svc", {"retry": {"max_attempts": 9}})
    r.get_breaker("svc")
    r.reset()
    cfg = r.get_config("svc")
    assert cfg.retry.max_attempts == 3
