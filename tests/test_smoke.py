"""Smoke tests — package boots and the M1 public surface is callable."""

from __future__ import annotations

import inspect
import re

import resilience_kit


def test_package_imports() -> None:
    assert resilience_kit is not None


def test_version_is_pep440() -> None:
    assert re.match(
        r"^\d+\.\d+\.\d+([.+-]?(a|b|rc|dev|post)\d+)?$",
        resilience_kit.__version__,
    ), resilience_kit.__version__


def test_m1_public_surface_is_callable() -> None:
    for name in (
        "retry",
        "retry_on_failure",
        "circuit_breaker",
        "resilient",
    ):
        attr = getattr(resilience_kit, name)
        assert callable(attr), name


def test_registry_singleton_present() -> None:
    assert resilience_kit.registry is not None
    assert isinstance(resilience_kit.registry, resilience_kit.ResilienceRegistry)


def test_decorators_emit_a_callable_wrapper() -> None:
    @resilience_kit.resilient("svc")
    async def upstream() -> int:
        return 1

    assert inspect.iscoroutinefunction(upstream)
