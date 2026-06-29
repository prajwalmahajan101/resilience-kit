"""Unit tests for :class:`OtelMetricsSink` (Lane C #C3). Needs the ``[otel]`` extra."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("opentelemetry")

from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from resilience_kit.metrics.otel import OtelMetricsSink

_reader = InMemoryMetricReader()


@pytest.fixture(scope="module", autouse=True)
def _meter_provider() -> None:
    """Install a module-local meter provider feeding an in-memory reader."""
    otel_metrics.set_meter_provider(MeterProvider(metric_readers=[_reader]))


def _points_for(name: str) -> list[Any]:
    data = _reader.get_metrics_data()
    points: list[Any] = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == name:
                    points.extend(metric.data.data_points)
    return points


def test_counter_records_measurement() -> None:
    """incr() produces a namespaced counter measurement."""
    sink = OtelMetricsSink()
    sink.incr("breaker.open", 2.0)
    points = _points_for("resilience_kit.breaker.open")
    assert points
    assert sum(p.value for p in points) == 2.0


def test_histogram_records_measurement() -> None:
    """timing() produces a histogram measurement with the recorded sum."""
    sink = OtelMetricsSink()
    sink.timing("http.latency", 30.0)
    points = _points_for("resilience_kit.http.latency")
    assert points
    assert any(p.sum == 30.0 for p in points)


def test_gauge_records_value() -> None:
    """gauge() produces a gauge measurement with the last value."""
    sink = OtelMetricsSink()
    sink.gauge("pool.size", 5.0)
    points = _points_for("resilience_kit.pool.size")
    assert points
    assert any(p.value == 5.0 for p in points)


def test_tags_become_attributes() -> None:
    """Tags pass through as measurement attributes."""
    sink = OtelMetricsSink()
    sink.incr("retry.exhausted", tags={"service": "partner"})
    points = _points_for("resilience_kit.retry.exhausted")
    assert any(p.attributes.get("service") == "partner" for p in points)
