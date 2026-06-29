"""Sentry-backed metrics sink (Lane C #C4). Extra: ``[sentry]``.

A `MetricsSink` that tees the kit's *significant* failure signals into Sentry as
breadcrumbs — so when an exception is later captured, the Sentry event carries a
trail of `breaker.open` / `retry.exhausted` / `throttle.fail_closed` events that
led up to it. Each breadcrumb's ``data`` carries the kit's ``request_id`` /
``correlation_id`` ContextVars plus the metric tags, so the breadcrumb correlates
with the rest of your logs.

This sink is *terminal* (it does not forward to another sink). Use it when Sentry
breadcrumbs are the observability you want from kit metrics; for Prometheus/OTel
counters run one of those sinks instead. Select via
``RESILIENCE_METRICS_SINK=sentry``. Wrap with
:class:`~resilience_kit.metrics.cardinality.BoundedMetricsSink`
(``settings.metrics_cardinality_budget``) as usual.

Setting ``request_id`` as a Sentry *tag* (vs. breadcrumb data) belongs in
request middleware, not a metrics sink — see ``docs/sentry-integration.md``.

Importing this module without the ``[sentry]`` extra raises
:class:`~resilience_kit.exceptions.MissingExtraError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resilience_kit.context import correlation_id, request_id
from resilience_kit.exceptions import MissingExtraError

try:
    import sentry_sdk
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("sentry", "resilience-kit[sentry]") from exc

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

#: Kit metric names that, by default, leave a Sentry breadcrumb. The
#: failure / degradation signals worth seeing in the trail before a crash.
DEFAULT_BREADCRUMB_METRICS: frozenset[str] = frozenset(
    {
        "breaker.open",
        "breaker.degraded",
        "retry.exhausted",
        "throttle.fail_closed",
        "throttle.degraded",
        "cache.degraded",
        "audit.write_failed",
        "audit.dropped",
    },
)

_BREADCRUMB_CATEGORY = "resilience_kit"


class SentryMetricsSink:
    """Tee significant kit metrics into Sentry as breadcrumbs."""

    def __init__(self, breadcrumb_metrics: Iterable[str] | None = None) -> None:
        """Configure which metric names emit a breadcrumb.

        Args:
            breadcrumb_metrics: Metric names that leave a breadcrumb. When
                ``None``, :data:`DEFAULT_BREADCRUMB_METRICS` is used.
        """
        self._breadcrumb_metrics = (
            frozenset(breadcrumb_metrics)
            if breadcrumb_metrics is not None
            else DEFAULT_BREADCRUMB_METRICS
        )

    def incr(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Leave a Sentry breadcrumb for a significant counter event."""
        if name in self._breadcrumb_metrics:
            self._breadcrumb(name, tags)

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Timings are not breadcrumbed (too frequent); intentionally a no-op."""

    def gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Gauges are not breadcrumbed; intentionally a no-op."""

    def _breadcrumb(self, name: str, tags: Mapping[str, str] | None) -> None:
        data: dict[str, str] = dict(tags) if tags else {}
        rid = request_id.get()
        if rid is not None:
            data.setdefault("request_id", rid)
        cid = correlation_id.get()
        if cid is not None:
            data.setdefault("correlation_id", cid)
        sentry_sdk.add_breadcrumb(
            category=_BREADCRUMB_CATEGORY,
            message=name,
            level="warning",
            data=data,
        )


__all__ = ["DEFAULT_BREADCRUMB_METRICS", "SentryMetricsSink"]
