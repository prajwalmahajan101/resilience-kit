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


_lock = threading.Lock()
_sink: MetricsSink = NoopMetricsSink()


def get_metrics() -> MetricsSink:
    """Return the currently-installed metrics sink.

    Returns:
        The active :class:`MetricsSink`.
    """
    return _sink


def set_metrics(sink: MetricsSink) -> None:
    """Install ``sink`` as the global metrics sink.

    Args:
        sink: New sink instance.
    """
    global _sink  # noqa: PLW0603 — module-level swap is the API
    with _lock:
        _sink = sink


def reset_metrics() -> None:
    """Restore the default no-op sink. Wired into ``testing.reset_all_singletons``."""
    set_metrics(NoopMetricsSink())
