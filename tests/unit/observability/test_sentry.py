"""Unit tests for :class:`SentryMetricsSink` (Lane C #C4). Needs the extra."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("sentry_sdk")

import sentry_sdk

from resilience_kit.context import bind
from resilience_kit.observability.sentry import (
    DEFAULT_BREADCRUMB_METRICS,
    SentryMetricsSink,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def captured_events() -> Iterator[list[dict[str, Any]]]:
    """Init Sentry with a capturing transport; yield the captured event list."""
    events: list[dict[str, Any]] = []
    sentry_sdk.init(
        dsn="http://key@localhost/1",
        transport=events.append,
        default_integrations=False,
        auto_enabling_integrations=False,
    )
    # The isolation scope persists across init() calls; clear stale breadcrumbs
    # from previous tests so each test starts with an empty trail.
    sentry_sdk.get_isolation_scope().clear_breadcrumbs()
    sentry_sdk.get_current_scope().clear_breadcrumbs()
    yield events
    sentry_sdk.get_isolation_scope().clear_breadcrumbs()
    sentry_sdk.get_current_scope().clear_breadcrumbs()
    # Drop the client so breadcrumbs/scope don't leak into other tests.
    sentry_sdk.init(dsn=None)


def _breadcrumbs(event: dict[str, Any]) -> list[dict[str, Any]]:
    crumbs = event.get("breadcrumbs")
    if isinstance(crumbs, dict):  # sentry sends {"values": [...]}
        result: list[dict[str, Any]] = crumbs["values"]
        return result
    return crumbs or []


def test_significant_event_leaves_breadcrumb(
    captured_events: list[dict[str, Any]],
) -> None:
    """A breaker.open metric becomes a breadcrumb on the next captured event."""
    sink = SentryMetricsSink()
    with bind(request_id_value="rid-1", correlation_id_value="cid-2"):
        sink.incr("breaker.open", tags={"service": "partner"})
        sentry_sdk.capture_message("boom")
    sentry_sdk.flush()

    crumbs = _breadcrumbs(captured_events[0])
    breaker_crumbs = [c for c in crumbs if c["message"] == "breaker.open"]
    assert len(breaker_crumbs) == 1
    data = breaker_crumbs[0]["data"]
    assert data["service"] == "partner"
    assert data["request_id"] == "rid-1"
    assert data["correlation_id"] == "cid-2"
    assert breaker_crumbs[0]["category"] == "resilience_kit"


def test_insignificant_metric_leaves_no_breadcrumb(
    captured_events: list[dict[str, Any]],
) -> None:
    """A non-failure metric (breaker.success) does not breadcrumb."""
    sink = SentryMetricsSink()
    sink.incr("breaker.success", tags={"service": "x"})
    sentry_sdk.capture_message("boom")
    sentry_sdk.flush()

    crumbs = _breadcrumbs(captured_events[0])
    assert not [c for c in crumbs if c["message"] == "breaker.success"]


def test_timing_and_gauge_are_noops(captured_events: list[dict[str, Any]]) -> None:
    """timing()/gauge() never breadcrumb (too frequent)."""
    sink = SentryMetricsSink()
    sink.timing("http.latency", 12.0, tags={"service": "x"})
    sink.gauge("pool.size", 3.0)
    sentry_sdk.capture_message("boom")
    sentry_sdk.flush()
    assert _breadcrumbs(captured_events[0]) == []


def test_custom_breadcrumb_set(captured_events: list[dict[str, Any]]) -> None:
    """A custom metric set overrides the default failure set."""
    sink = SentryMetricsSink(breadcrumb_metrics={"custom.alarm"})
    sink.incr("breaker.open")  # not in custom set → no crumb
    sink.incr("custom.alarm")  # in custom set → crumb
    sentry_sdk.capture_message("boom")
    sentry_sdk.flush()

    messages = {c["message"] for c in _breadcrumbs(captured_events[0])}
    assert "custom.alarm" in messages
    assert "breaker.open" not in messages


def test_default_set_covers_key_failure_signals() -> None:
    """The default breadcrumb set includes the headline failure metrics."""
    assert {"breaker.open", "retry.exhausted", "throttle.fail_closed"} <= (
        DEFAULT_BREADCRUMB_METRICS
    )
