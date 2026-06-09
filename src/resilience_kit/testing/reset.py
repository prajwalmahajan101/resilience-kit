"""Reset every kit-managed singleton — used by test fixtures.

Adapters (Django, FastAPI) typically wire this into an autouse fixture in
their integration test suites. Library users can call it explicitly between
tests that mutate kit state.
"""

from __future__ import annotations

from resilience_kit.cache.provider import reset_cache
from resilience_kit.metrics import reset_metrics
from resilience_kit.recovery import reset_recovery_state
from resilience_kit.registry import reset_registry
from resilience_kit.runtime import reset_settings_cache
from resilience_kit.throttle.provider import reset_throttle


def reset_all_singletons() -> None:
    """Reset settings cache, registry, providers, recovery roster, metrics sink.

    Adds future reset hooks for ``audit.dispatch`` etc. when those
    modules ship in M4.
    """
    reset_settings_cache()
    reset_registry()
    reset_cache()
    reset_throttle()
    reset_recovery_state()
    reset_metrics()
    # The Fernet cipher is behind an optional extra; only reset when the
    # extra is installed so importing the kit without `[crypto]` still
    # runs the full reset.
    try:
        from resilience_kit.crypto.fernet import reset_fernet_cache  # noqa: PLC0415

        reset_fernet_cache()
    except ImportError:
        pass
    # M4 audit + tasks: clear lazily-built dispatchers so cross-test
    # event-loop reuse does not bind a Queue to a closed loop.
    from resilience_kit.audit.factory import reset_dispatcher  # noqa: PLC0415
    from resilience_kit.tasks.queue import reset_tasks  # noqa: PLC0415
    from resilience_kit.tasks.registry import reset_registry as reset_task_registry  # noqa: PLC0415

    reset_dispatcher()
    reset_tasks()
    reset_task_registry()
