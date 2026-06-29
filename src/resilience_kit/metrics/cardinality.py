"""Cardinality-bounded metrics sink wrapper (Lane C, ADR-0015).

A `MetricsSink` that forwards to an inner sink but caps the number of
distinct tag-value combinations recorded per metric name. The single
biggest production-risk with a "log this dict" sink is an unbounded label
(e.g. a `request_id` slipping into `tags`): Prometheus/OTel then mint a new
time series per value and the backend's memory explodes.

`BoundedMetricsSink` admits up to ``cardinality_budget`` distinct tag
combinations per metric; beyond that it drops the *labels* (still records
the metric, just unlabelled) and emits ``metrics.cardinality_exceeded``
once per metric so the regression is observable rather than silent.

See ADR-0015 for the contract and rationale.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from resilience_kit.metrics import MetricsSink

_logger = logging.getLogger(__name__)

#: Default budget — distinct tag combinations allowed per metric name.
DEFAULT_CARDINALITY_BUDGET = 50

#: Metric emitted (unlabelled) the first time a metric blows its budget.
CARDINALITY_EXCEEDED_METRIC = "metrics.cardinality_exceeded"


class BoundedMetricsSink:
    """Wrap a `MetricsSink`, capping distinct tag combos per metric name."""

    def __init__(
        self,
        inner: MetricsSink,
        *,
        cardinality_budget: int = DEFAULT_CARDINALITY_BUDGET,
    ) -> None:
        """Wrap ``inner`` with a per-metric cardinality cap.

        Args:
            inner: The sink that actually records admitted events.
            cardinality_budget: Max distinct tag-value combinations per
                metric name before labels are dropped.
        """
        self._inner = inner
        self._budget = cardinality_budget
        self._seen: dict[str, set[tuple[tuple[str, str], ...]]] = {}
        self._warned: set[str] = set()
        self._lock = threading.Lock()

    def _admit(
        self,
        name: str,
        tags: Mapping[str, str] | None,
    ) -> Mapping[str, str] | None:
        """Return ``tags`` if within budget, else ``None`` (drop labels)."""
        if not tags:
            return tags
        combo = tuple(sorted(tags.items()))
        warn = False
        with self._lock:
            seen = self._seen.setdefault(name, set())
            if combo in seen:
                return tags
            if len(seen) < self._budget:
                seen.add(combo)
                return tags
            if name not in self._warned:
                self._warned.add(name)
                warn = True
        if warn:
            _logger.warning(
                "metric %r exceeded its cardinality budget (%d distinct tag "
                "combinations); dropping labels for further values. Check for a "
                "high-cardinality tag (request_id, user_id, raw URL).",
                name,
                self._budget,
            )
            # Unlabelled so this counter cannot itself explode cardinality.
            self._inner.incr(CARDINALITY_EXCEEDED_METRIC, 1.0, {"metric": name})
        return None

    def incr(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Forward an increment, capping label cardinality first."""
        self._inner.incr(name, value, self._admit(name, tags))

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Forward a timing, capping label cardinality first."""
        self._inner.timing(name, value_ms, self._admit(name, tags))

    def gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Forward a gauge, capping label cardinality first."""
        self._inner.gauge(name, value, self._admit(name, tags))


__all__ = [
    "CARDINALITY_EXCEEDED_METRIC",
    "DEFAULT_CARDINALITY_BUDGET",
    "BoundedMetricsSink",
]
