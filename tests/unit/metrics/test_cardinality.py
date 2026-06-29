"""Unit tests for :class:`BoundedMetricsSink` (Lane C #C2, ADR-0015)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from resilience_kit.metrics.cardinality import (
    CARDINALITY_EXCEEDED_METRIC,
    BoundedMetricsSink,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class _Recording:
    """Inner sink that records every forwarded call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float, dict[str, str] | None]] = []

    def incr(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        self.calls.append(("incr", name, value, dict(tags) if tags else None))

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        self.calls.append(("timing", name, value_ms, dict(tags) if tags else None))

    def gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        self.calls.append(("gauge", name, value, dict(tags) if tags else None))


def test_within_budget_passes_tags_through() -> None:
    """Distinct combos under the budget are forwarded with their tags."""
    inner = _Recording()
    sink = BoundedMetricsSink(inner, cardinality_budget=3)
    for i in range(3):
        sink.incr("breaker.open", tags={"service": f"svc{i}"})
    assert [c[3] for c in inner.calls] == [
        {"service": "svc0"},
        {"service": "svc1"},
        {"service": "svc2"},
    ]


def test_repeated_combo_does_not_consume_budget() -> None:
    """Re-using a seen combo never counts against the budget."""
    inner = _Recording()
    sink = BoundedMetricsSink(inner, cardinality_budget=1)
    sink.incr("retry.attempt", tags={"service": "a"})
    sink.incr("retry.attempt", tags={"service": "a"})
    sink.incr("retry.attempt", tags={"service": "a"})
    # All three forwarded with tags; budget of 1 not exceeded.
    assert all(c[3] == {"service": "a"} for c in inner.calls)


def test_over_budget_drops_labels_and_warns_once() -> None:
    """Beyond the budget, labels are dropped and the overflow metric fires once."""
    inner = _Recording()
    sink = BoundedMetricsSink(inner, cardinality_budget=2)
    sink.incr("throttle.degraded", tags={"k": "a"})  # admitted
    sink.incr("throttle.degraded", tags={"k": "b"})  # admitted (budget=2)
    sink.incr("throttle.degraded", tags={"k": "c"})  # over budget
    sink.incr("throttle.degraded", tags={"k": "d"})  # over budget

    degraded = [c for c in inner.calls if c[1] == "throttle.degraded"]
    assert degraded[0][3] == {"k": "a"}
    assert degraded[1][3] == {"k": "b"}
    assert degraded[2][3] is None  # labels dropped
    assert degraded[3][3] is None

    overflow = [c for c in inner.calls if c[1] == CARDINALITY_EXCEEDED_METRIC]
    assert len(overflow) == 1  # emitted once, not per over-budget call
    assert overflow[0][3] == {"metric": "throttle.degraded"}


def test_untagged_events_always_pass() -> None:
    """Events with no tags are forwarded untouched regardless of budget."""
    inner = _Recording()
    sink = BoundedMetricsSink(inner, cardinality_budget=0)
    sink.incr("breaker.success")
    sink.timing("retry.latency", 12.0)
    sink.gauge("pool.size", 4.0)
    assert [(c[0], c[1], c[3]) for c in inner.calls] == [
        ("incr", "breaker.success", None),
        ("timing", "retry.latency", None),
        ("gauge", "pool.size", None),
    ]
