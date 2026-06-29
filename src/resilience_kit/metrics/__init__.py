"""Pluggable metrics sink — RED metrics for retry, breaker, throttle, http_client.

The kit emits metric events through a tiny :class:`MetricsSink` protocol;
real sinks are wired in by the caller. Builtin sinks: :class:`NoopMetricsSink`
(default) and :class:`StdlibLoggingMetricsSink`. The ``[prometheus]`` extra adds
``resilience_kit.metrics.prometheus.PrometheusMetricsSink`` and the ``[otel]``
extra adds ``resilience_kit.metrics.otel.OtelMetricsSink`` — both loaded only
when selected, so this package imports cleanly without those deps installed.

:class:`~resilience_kit.metrics.cardinality.BoundedMetricsSink` wraps any sink
to cap label cardinality; enable it via ``settings.metrics_cardinality_budget``.
The :func:`record_counter` / :func:`record_duration` / :func:`record_gauge`
free functions are a thin shim over :func:`get_metrics` for call sites that
prefer functions to holding a sink reference.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from resilience_kit.metrics.cardinality import BoundedMetricsSink

if TYPE_CHECKING:
    from collections.abc import Mapping


_logger = logging.getLogger(__name__)


@runtime_checkable
class MetricsSink(Protocol):
    """Receive metric events.

    Implementations may be sync (cheap counters/timers) or batch internally;
    callers MUST NOT block in these methods.
    """

    def incr(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Increment a counter.

        Args:
            name: Dotted metric name.
            value: Increment value (usually ``1.0``).
            tags: Optional low-cardinality dimension labels.
        """
        ...

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Record a duration in milliseconds.

        Args:
            name: Dotted metric name.
            value_ms: Duration in milliseconds.
            tags: Optional dimension labels.
        """
        ...

    def gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Set a gauge to the given value.

        Args:
            name: Dotted metric name.
            value: Current value.
            tags: Optional dimension labels.
        """
        ...


class NoopMetricsSink:
    """Default sink — drops every event silently. Zero overhead."""

    def incr(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Discard the event."""

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Discard the event."""

    def gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Discard the event."""


class StdlibLoggingMetricsSink:
    """Log metric events at DEBUG level — useful in dev, not in prod."""

    def incr(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Log the increment at DEBUG."""
        _logger.debug("metric.incr name=%s value=%s tags=%s", name, value, tags or {})

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Log the timing at DEBUG."""
        _logger.debug("metric.timing name=%s value_ms=%s tags=%s", name, value_ms, tags or {})

    def gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Log the gauge at DEBUG."""
        _logger.debug("metric.gauge name=%s value=%s tags=%s", name, value, tags or {})


_METRICS_GROUP = "resilience_kit.metrics_sinks"
_BUILTIN_SINKS: Mapping[str, type[MetricsSink]] = {
    "noop": NoopMetricsSink,
    "stdlib_logging": StdlibLoggingMetricsSink,
}

_lock = threading.Lock()
_sink: MetricsSink | None = None


def get_metrics() -> MetricsSink:
    """Return the active metrics sink, resolving lazily from settings.

    Resolution order — used the first time a sink is needed, then cached:

    1. Whatever the caller passed to :func:`set_metrics`.
    2. ``settings.metrics_sink`` resolved through the standard provider
       chain (explicit instance → importable string → entry point →
       builtin ``"noop"`` / ``"stdlib_logging"`` → fail).

    Returns:
        The active :class:`MetricsSink`.
    """
    global _sink  # noqa: PLW0603
    if _sink is not None:
        return _sink
    with _lock:
        if _sink is None:
            _sink = _resolve_from_settings()
    return _sink


def _resolve_from_settings() -> MetricsSink:
    """Build a sink from ``settings.metrics_sink`` via the provider chain.

    Imported lazily inside the function to avoid a settings ↔ metrics
    import cycle at module load.
    """
    from resilience_kit._providers import resolve_provider  # noqa: PLC0415
    from resilience_kit.exceptions import UnknownBackendError  # noqa: PLC0415
    from resilience_kit.runtime import get_settings  # noqa: PLC0415

    settings = get_settings()
    name = settings.metrics_sink
    try:
        sink: MetricsSink = resolve_provider(
            group=_METRICS_GROUP,
            name=name,
            builtins=_BUILTIN_SINKS,
        )
    except UnknownBackendError:
        _logger.warning(
            "metrics_sink=%r did not resolve; falling back to no-op.",
            name,
        )
        sink = NoopMetricsSink()

    budget = settings.metrics_cardinality_budget
    if budget is not None:
        return BoundedMetricsSink(sink, cardinality_budget=budget)
    return sink


def set_metrics(sink: MetricsSink) -> None:
    """Install ``sink`` as the global metrics sink.

    Args:
        sink: New sink instance. Wins over the settings-driven default.
    """
    global _sink  # noqa: PLW0603 — module-level swap is the API
    with _lock:
        _sink = sink


def reset_metrics() -> None:
    """Restore lazy resolution. Wired into ``testing.reset_all_singletons``."""
    global _sink  # noqa: PLW0603
    with _lock:
        _sink = None


# --- Free-function shim over the resolved sink ------------------------------
# Lets call sites record metrics without threading a MetricsSink reference
# through, while still teeing into the pluggable backend.


def record_counter(
    name: str,
    value: float = 1.0,
    tags: Mapping[str, str] | None = None,
) -> None:
    """Increment a counter on the active sink (see :meth:`MetricsSink.incr`)."""
    get_metrics().incr(name, value, tags)


def record_duration(
    name: str,
    value_ms: float,
    tags: Mapping[str, str] | None = None,
) -> None:
    """Record a duration on the active sink (see :meth:`MetricsSink.timing`)."""
    get_metrics().timing(name, value_ms, tags)


def record_gauge(
    name: str,
    value: float,
    tags: Mapping[str, str] | None = None,
) -> None:
    """Set a gauge on the active sink (see :meth:`MetricsSink.gauge`)."""
    get_metrics().gauge(name, value, tags)


__all__ = [
    "BoundedMetricsSink",
    "MetricsSink",
    "NoopMetricsSink",
    "StdlibLoggingMetricsSink",
    "get_metrics",
    "record_counter",
    "record_duration",
    "record_gauge",
    "reset_metrics",
    "set_metrics",
]
