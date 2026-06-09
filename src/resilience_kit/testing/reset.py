"""Reset every kit-managed singleton — used by test fixtures.

Adapters (Django, FastAPI) typically wire this into an autouse fixture in
their integration test suites. Library users can call it explicitly between
tests that mutate kit state.
"""

from __future__ import annotations

from resilience_kit.cache.provider import reset_cache
from resilience_kit.metrics import reset_metrics
from resilience_kit.registry import reset_registry
from resilience_kit.runtime import reset_settings_cache
from resilience_kit.throttle.provider import reset_throttle


def reset_all_singletons() -> None:
    """Reset settings cache, registry, providers, and metrics sink.

    Adds future reset hooks for ``recovery``, ``audit.dispatch``, etc. when
    those modules ship in M2 / M4.
    """
    reset_settings_cache()
    reset_registry()
    reset_cache()
    reset_throttle()
    reset_metrics()
