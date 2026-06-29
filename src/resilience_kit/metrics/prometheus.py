"""`prometheus_client`-backed metrics sink (Lane C #C2). Extra: ``[prometheus]``.

Maps the kit's `MetricsSink` calls onto Prometheus instruments:

* ``incr`` → `Counter` (``..._total``)
* ``timing`` → `Histogram` (observed in milliseconds)
* ``gauge`` → `Gauge`

Dotted kit metric names (``breaker.open``, ``retry.exhausted``,
``throttle.fail_closed`` …) are sanitised to valid Prometheus names under the
``resilience_kit_`` namespace. Label *names* for a metric are fixed on first
sight (Prometheus requires a stable label set per series); later calls fill
missing labels with ``""`` and ignore extras, so a varying tag set degrades
gracefully instead of raising.

Importing this module without the ``[prometheus]`` extra raises
:class:`~resilience_kit.exceptions.MissingExtraError` — it is only imported when
the ``prometheus`` sink is selected, so the base ``metrics`` package stays
import-clean.

Pair with :class:`~resilience_kit.metrics.cardinality.BoundedMetricsSink`
(``settings.metrics_cardinality_budget``) in production so a stray
high-cardinality label cannot mint unbounded series.
"""

from __future__ import annotations

import re
import threading
from typing import TYPE_CHECKING

from resilience_kit.exceptions import MissingExtraError

try:
    from prometheus_client import REGISTRY, Counter, Gauge, Histogram
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("prometheus", "resilience-kit[prometheus]") from exc

if TYPE_CHECKING:
    from collections.abc import Mapping

    from prometheus_client.registry import CollectorRegistry

_NAMESPACE = "resilience_kit"
_INVALID = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize(name: str) -> str:
    """Map a dotted kit metric name to a valid Prometheus metric name."""
    return f"{_NAMESPACE}_{_INVALID.sub('_', name)}"


class PrometheusMetricsSink:
    """Record kit metrics on Prometheus instruments."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Create the sink.

        Args:
            registry: Collector registry to register instruments on.
                Defaults to the global ``prometheus_client.REGISTRY`` so a
                stock ``/metrics`` endpoint scrapes kit metrics out of the
                box. Tests should pass a fresh ``CollectorRegistry()`` to
                avoid duplicate-registration across instances.
        """
        self._registry = registry if registry is not None else REGISTRY
        self._counters: dict[str, tuple[Counter, tuple[str, ...]]] = {}
        self._histograms: dict[str, tuple[Histogram, tuple[str, ...]]] = {}
        self._gauges: dict[str, tuple[Gauge, tuple[str, ...]]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _label_values(
        labelnames: tuple[str, ...],
        tags: Mapping[str, str] | None,
    ) -> list[str]:
        tags = tags or {}
        return [str(tags.get(name, "")) for name in labelnames]

    def incr(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Increment the counter for ``name``."""
        counter, labelnames = self._counter(name, tags)
        if labelnames:
            counter.labels(*self._label_values(labelnames, tags)).inc(value)
        else:
            counter.inc(value)

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Observe ``value_ms`` on the histogram for ``name``."""
        hist, labelnames = self._histogram(name, tags)
        if labelnames:
            hist.labels(*self._label_values(labelnames, tags)).observe(value_ms)
        else:
            hist.observe(value_ms)

    def gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Set the gauge for ``name``."""
        gauge, labelnames = self._gauge(name, tags)
        if labelnames:
            gauge.labels(*self._label_values(labelnames, tags)).set(value)
        else:
            gauge.set(value)

    def _counter(
        self,
        name: str,
        tags: Mapping[str, str] | None,
    ) -> tuple[Counter, tuple[str, ...]]:
        with self._lock:
            existing = self._counters.get(name)
            if existing is not None:
                return existing
            labelnames = tuple(sorted(tags)) if tags else ()
            counter = Counter(
                _sanitize(name),
                f"resilience-kit counter {name}",
                labelnames,
                registry=self._registry,
            )
            self._counters[name] = (counter, labelnames)
            return counter, labelnames

    def _histogram(
        self,
        name: str,
        tags: Mapping[str, str] | None,
    ) -> tuple[Histogram, tuple[str, ...]]:
        with self._lock:
            existing = self._histograms.get(name)
            if existing is not None:
                return existing
            labelnames = tuple(sorted(tags)) if tags else ()
            hist = Histogram(
                f"{_sanitize(name)}_milliseconds",
                f"resilience-kit timing {name} (ms)",
                labelnames,
                registry=self._registry,
            )
            self._histograms[name] = (hist, labelnames)
            return hist, labelnames

    def _gauge(
        self,
        name: str,
        tags: Mapping[str, str] | None,
    ) -> tuple[Gauge, tuple[str, ...]]:
        with self._lock:
            existing = self._gauges.get(name)
            if existing is not None:
                return existing
            labelnames = tuple(sorted(tags)) if tags else ()
            gauge = Gauge(
                _sanitize(name),
                f"resilience-kit gauge {name}",
                labelnames,
                registry=self._registry,
            )
            self._gauges[name] = (gauge, labelnames)
            return gauge, labelnames


__all__ = ["PrometheusMetricsSink"]
