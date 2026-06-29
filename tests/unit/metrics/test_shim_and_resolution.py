"""Free-function shim + cardinality-wrap resolution (Lane C #C2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resilience_kit.metrics import (
    BoundedMetricsSink,
    NoopMetricsSink,
    get_metrics,
    record_counter,
    record_duration,
    record_gauge,
    reset_metrics,
    set_metrics,
)
from resilience_kit.runtime import set_settings_source
from resilience_kit.settings import ResilienceSettings

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


class _FixedSource:
    def __init__(self, settings: ResilienceSettings) -> None:
        self._settings = settings

    def load(self) -> ResilienceSettings:
        return self._settings


class _Recording:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def incr(self, name: str, value: float = 1.0, tags: Mapping[str, str] | None = None) -> None:
        self.calls.append(("incr", name, value))

    def timing(self, name: str, value_ms: float, tags: Mapping[str, str] | None = None) -> None:
        self.calls.append(("timing", name, value_ms))

    def gauge(self, name: str, value: float, tags: Mapping[str, str] | None = None) -> None:
        self.calls.append(("gauge", name, value))


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    reset_metrics()
    yield
    reset_metrics()


def test_shim_routes_to_active_sink() -> None:
    """record_* forward to whatever sink is installed."""
    sink = _Recording()
    set_metrics(sink)
    record_counter("breaker.open", 2.0)
    record_duration("http.latency", 15.0)
    record_gauge("pool.size", 3.0)
    assert sink.calls == [
        ("incr", "breaker.open", 2.0),
        ("timing", "http.latency", 15.0),
        ("gauge", "pool.size", 3.0),
    ]


def test_cardinality_budget_wraps_resolved_sink() -> None:
    """metrics_cardinality_budget wraps the resolved sink in BoundedMetricsSink."""
    set_settings_source(
        _FixedSource(
            ResilienceSettings(metrics_sink="noop", metrics_cardinality_budget=10),
        ),
    )
    sink = get_metrics()
    assert isinstance(sink, BoundedMetricsSink)


def test_no_budget_leaves_sink_unwrapped() -> None:
    """Without a budget the resolved sink is returned as-is (non-breaking)."""
    set_settings_source(_FixedSource(ResilienceSettings(metrics_sink="noop")))
    assert isinstance(get_metrics(), NoopMetricsSink)


def test_prometheus_resolves_via_entry_point() -> None:
    """metrics_sink='prometheus' resolves the exporter through its entry point."""
    pytest.importorskip("prometheus_client")
    from resilience_kit.metrics.prometheus import PrometheusMetricsSink  # noqa: PLC0415

    set_settings_source(_FixedSource(ResilienceSettings(metrics_sink="prometheus")))
    assert isinstance(get_metrics(), PrometheusMetricsSink)
