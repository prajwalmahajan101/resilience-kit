# 0015 — Metrics exporter strategy + cardinality contract

Status: accepted  ·  Date: 2026-06-29  ·  Milestone: v0.2.0 (Lane C #C2)

## Context

v0.1 shipped a `MetricsSink` protocol (`incr` / `timing` / `gauge`) with only
`noop` and `stdlib_logging` builtins — a pluggable interface with no real
exporter, so observability was "theatre." Lane C #C2 adds a `prometheus_client`
exporter (and #C3 an OTel one).

The M7 FastAPI/Django dogfooding reports independently flagged the **single
biggest production risk** in the v0.1 metrics design: the sink takes an
arbitrary `tags: Mapping[str, str]`, and the first time a high-cardinality value
(a `request_id`, a raw URL, a user id) slips into `tags` past code review, a
pull-based backend like Prometheus mints a new time series per value and the
scrape target's memory explodes. A "log this dict" sink hides the blast radius
until it detonates in prod.

## Decision

Two pieces ship together, because an exporter without a cardinality guard ships
the footgun loaded:

1. **`PrometheusMetricsSink`** (`metrics/prometheus.py`, `[prometheus]` extra)
   maps `incr → Counter`, `timing → Histogram` (ms), `gauge → Gauge`, under a
   `resilience_kit_` namespace, with dotted names sanitised. Label names per
   metric are fixed on first sight (Prometheus requires a stable label set);
   later calls fill missing labels with `""` and ignore extras so a varying tag
   set degrades instead of raising. Defaults to the global `REGISTRY` so a stock
   `/metrics` works; tests inject a fresh `CollectorRegistry`. It lives in a
   submodule imported only when selected, so the base `metrics` package imports
   without the extra.

2. **`BoundedMetricsSink`** (`metrics/cardinality.py`) wraps any sink and caps
   distinct tag-value combinations per metric at a budget. Beyond the budget it
   **drops the labels** (still records the metric, unlabelled) and emits
   `metrics.cardinality_exceeded{metric=...}` once per metric. Enabled via
   `settings.metrics_cardinality_budget` (default `None` = off, so the change is
   non-breaking for `noop`/`stdlib`); the resolver wraps the resolved sink when
   a budget is set.

Also ship a `record_counter` / `record_duration` / `record_gauge` **free-function
shim** over `get_metrics()` so call sites can record without holding a sink
reference — requested by the Django dogfooding report.

`metrics.py` becomes the `metrics/` package; all v0.1 public names
(`MetricsSink`, `get_metrics`, `set_metrics`, `reset_metrics`, the two builtins)
re-export unchanged from `resilience_kit.metrics`.

## Consequences

- The Prometheus exporter is real and `/metrics`-ready; the cardinality guard
  makes the label footgun observable (a counter to alert on) instead of fatal.
- Dropping labels over budget rather than dropping the event keeps the aggregate
  count correct while bounding series growth — the right trade-off for RED
  metrics where the totals matter more than the breakdown.
- Default behaviour is unchanged unless an operator sets a budget, so existing
  `noop`/`stdlib` deployments see no difference.
- The budget is a blunt per-metric cap, not a per-label policy. A future
  refinement could allowlist specific label keys; out of scope here.
- Histograms use default buckets in milliseconds; tuning buckets per metric is
  deferred until an adopter needs it.

## Usage

```python
# Settings (env):
#   RESILIENCE_METRICS_SINK=prometheus
#   RESILIENCE_METRICS_CARDINALITY_BUDGET=100

# FastAPI /metrics endpoint:
from prometheus_client import make_asgi_app
app.mount("/metrics", make_asgi_app())

# Free-function shim:
from resilience_kit.metrics import record_counter
record_counter("custom.event", tags={"kind": "x"})
```
