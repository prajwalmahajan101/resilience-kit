"""OpenTelemetry-backed metrics sink (Lane C #C3). Extra: ``[otel]``.

Maps the kit's `MetricsSink` calls onto the OTel metrics API:

* ``incr`` → `Counter.add`
* ``timing`` → `Histogram.record` (milliseconds)
* ``gauge`` → `Gauge.set`

Instruments are created lazily under the ``resilience_kit.`` namespace and
cached per metric name. Unlike Prometheus, the OTel API accepts arbitrary
attributes per call, so tags map straight through as span/measurement
attributes — pair with
:class:`~resilience_kit.metrics.cardinality.BoundedMetricsSink` to keep
attribute cardinality bounded.

Importing this module without the ``[otel]`` extra raises
:class:`~resilience_kit.exceptions.MissingExtraError`; it is imported only when
the ``otel`` sink is selected, so the base ``metrics`` package stays clean.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from resilience_kit.exceptions import MissingExtraError

try:
    from opentelemetry import metrics as otel_metrics
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("otel", "resilience-kit[otel]") from exc

if TYPE_CHECKING:
    from collections.abc import Mapping

    from opentelemetry.metrics import Counter, Histogram

    # The synchronous Gauge type is not re-exported publicly by the OTel
    # metrics package across versions; type it loosely.
    Gauge = Any

_NAMESPACE = "resilience_kit."


class OtelMetricsSink:
    """Record kit metrics on OpenTelemetry instruments."""

    def __init__(self, meter_name: str = "resilience_kit") -> None:
        """Create the sink.

        Args:
            meter_name: Name of the OTel meter to acquire from the globally
                configured ``MeterProvider``. With no provider configured the
                API is a no-op, so importing this never forces an exporter.
        """
        self._meter = otel_metrics.get_meter(meter_name)
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}
        self._gauges: dict[str, Gauge] = {}
        self._lock = threading.Lock()

    def incr(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Add ``value`` to the counter for ``name``."""
        self._counter(name).add(value, attributes=dict(tags) if tags else None)

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Record ``value_ms`` on the histogram for ``name``."""
        self._histogram(name).record(value_ms, attributes=dict(tags) if tags else None)

    def gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Set the gauge for ``name``."""
        self._gauge(name).set(value, attributes=dict(tags) if tags else None)

    def _counter(self, name: str) -> Counter:
        with self._lock:
            counter = self._counters.get(name)
            if counter is None:
                counter = self._meter.create_counter(f"{_NAMESPACE}{name}")
                self._counters[name] = counter
            return counter

    def _histogram(self, name: str) -> Histogram:
        with self._lock:
            hist = self._histograms.get(name)
            if hist is None:
                hist = self._meter.create_histogram(
                    f"{_NAMESPACE}{name}",
                    unit="ms",
                )
                self._histograms[name] = hist
            return hist

    def _gauge(self, name: str) -> Gauge:
        with self._lock:
            gauge = self._gauges.get(name)
            if gauge is None:
                gauge = self._meter.create_gauge(f"{_NAMESPACE}{name}")
                self._gauges[name] = gauge
            return gauge


__all__ = ["OtelMetricsSink"]
