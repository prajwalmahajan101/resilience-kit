"""Pluggable metrics sink — RED metrics for retry, breaker, throttle, http_client.

The kit emits metric events through a tiny :class:`MetricsSink` protocol;
real sinks (Prometheus, OTel, statsd) are wired in by the caller. Builtin
sinks: :class:`NoopMetricsSink` (default) and :class:`StdlibLoggingMetricsSink`
(M4 ships a real factory).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

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

    name = get_settings().metrics_sink
    try:
        return resolve_provider(
            group=_METRICS_GROUP,
            name=name,
            builtins=_BUILTIN_SINKS,
        )
    except UnknownBackendError:
        _logger.warning(
            "metrics_sink=%r did not resolve; falling back to no-op.",
            name,
        )
        return NoopMetricsSink()


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
