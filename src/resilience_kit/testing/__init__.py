"""Testing helpers — fakes and singleton-reset.

Public surface: :class:`Clock`, :class:`SystemClock`, :class:`FakeClock`,
:class:`FakeAuditSink`, :func:`reset_all_singletons`.

``reset_all_singletons`` is imported lazily to break the circular dependency
between the testing package and the primitives that themselves use
:class:`FakeClock` in test contexts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.testing.fakes import (
    Clock,
    FakeAuditSink,
    FakeClock,
    SystemClock,
)

if TYPE_CHECKING:
    from resilience_kit.testing.reset import reset_all_singletons


def __getattr__(name: str) -> Any:
    """Lazily resolve :func:`reset_all_singletons` to avoid an import cycle.

    Args:
        name: Attribute being looked up.

    Returns:
        The resolved attribute.

    Raises:
        AttributeError: ``name`` is not a known lazy export.
    """
    if name == "reset_all_singletons":
        from resilience_kit.testing.reset import (  # noqa: PLC0415 — lazy import breaks an init-time cycle
            reset_all_singletons as fn,
        )

        return fn
    raise AttributeError(f"module 'resilience_kit.testing' has no attribute {name!r}")


__all__ = [
    "Clock",
    "FakeAuditSink",
    "FakeClock",
    "SystemClock",
    "reset_all_singletons",
]
