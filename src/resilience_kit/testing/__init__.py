"""Testing helpers — fakes and singleton-reset.

Public surface: :class:`Clock`, :class:`SystemClock`, :class:`FakeClock`,
:class:`FakeAuditSink`, :func:`reset_all_singletons`,
:func:`reset_all_singletons_async`.

The reset helpers are imported lazily to break the circular dependency
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
    from resilience_kit.testing.reset import (
        reset_all_singletons,
        reset_all_singletons_async,
    )


def __getattr__(name: str) -> Any:
    """Lazily resolve :func:`reset_all_singletons` to avoid an import cycle.

    Args:
        name: Attribute being looked up.

    Returns:
        The resolved attribute.

    Raises:
        AttributeError: ``name`` is not a known lazy export.
    """
    if name in ("reset_all_singletons", "reset_all_singletons_async"):
        from resilience_kit.testing import reset  # noqa: PLC0415

        return getattr(reset, name)
    raise AttributeError(f"module 'resilience_kit.testing' has no attribute {name!r}")


__all__ = [
    "Clock",
    "FakeAuditSink",
    "FakeClock",
    "SystemClock",
    "reset_all_singletons",
    "reset_all_singletons_async",
]
