"""Unit tests for :class:`PrometheusMetricsSink` (Lane C #C2). Needs the extra."""

from __future__ import annotations

import pytest

pytest.importorskip("prometheus_client")

from prometheus_client import CollectorRegistry, generate_latest

from resilience_kit.metrics.prometheus import PrometheusMetricsSink


def _scrape(registry: CollectorRegistry) -> str:
    return generate_latest(registry).decode("utf-8")


def test_counter_increments_in_scrape() -> None:
    """incr() shows up as a sanitised, namespaced counter total."""
    reg = CollectorRegistry()
    sink = PrometheusMetricsSink(registry=reg)
    sink.incr("breaker.open")
    sink.incr("breaker.open")
    body = _scrape(reg)
    assert "resilience_kit_breaker_open_total 2.0" in body


def test_counter_with_labels() -> None:
    """Tags become Prometheus labels on the series."""
    reg = CollectorRegistry()
    sink = PrometheusMetricsSink(registry=reg)
    sink.incr("retry.exhausted", tags={"service": "partner"})
    body = _scrape(reg)
    assert 'resilience_kit_retry_exhausted_total{service="partner"} 1.0' in body


def test_timing_creates_histogram() -> None:
    """timing() observes onto a `_milliseconds` histogram."""
    reg = CollectorRegistry()
    sink = PrometheusMetricsSink(registry=reg)
    sink.timing("http.latency", 42.0)
    body = _scrape(reg)
    assert "resilience_kit_http_latency_milliseconds_count 1.0" in body
    assert "resilience_kit_http_latency_milliseconds_sum 42.0" in body


def test_gauge_sets_value() -> None:
    """gauge() sets the current value."""
    reg = CollectorRegistry()
    sink = PrometheusMetricsSink(registry=reg)
    sink.gauge("pool.in_use", 7.0)
    assert "resilience_kit_pool_in_use 7.0" in _scrape(reg)


def test_varying_tag_keys_degrade_gracefully() -> None:
    """A later call missing a label fills it with '' instead of raising."""
    reg = CollectorRegistry()
    sink = PrometheusMetricsSink(registry=reg)
    sink.incr("cache.degraded", tags={"alias": "default"})
    # Second call omits 'alias' — label names are fixed from the first call.
    sink.incr("cache.degraded")
    body = _scrape(reg)
    assert 'resilience_kit_cache_degraded_total{alias="default"} 1.0' in body
    assert 'resilience_kit_cache_degraded_total{alias=""} 1.0' in body
