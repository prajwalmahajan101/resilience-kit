# 0016 — OpenTelemetry trace-context propagation

Status: accepted  ·  Date: 2026-06-29  ·  Milestone: v0.2.0 (Lane C #C3)

## Context

After #C2 the kit exports metrics, but has no tracing story. Lane C #C3 adds an
OpenTelemetry surface: a metrics sink mapped to the OTel meter API, plus
distributed-trace context propagation so an inbound request and the outbound
calls it triggers land in one connected trace.

Two constraints shape the design:

1. **No hard OTel dependency.** OpenTelemetry is an optional `[otel]` extra. The
   core packages (`metrics`, `http_client`, `middleware`) must import and run
   with OTel absent.
2. **The kit already owns request identity.** `request_id` / `correlation_id`
   ContextVars are seeded by `RequestIdMiddleware`. Tracing should *enrich*
   spans with those ids, not replace them.

## Decision

- **`OtelMetricsSink`** (`metrics/otel.py`, `[otel]` extra, `otel` entry point)
  maps `incr → Counter.add`, `timing → Histogram.record` (ms), `gauge →
  Gauge.set`, under the `resilience_kit.` meter namespace. Unlike Prometheus the
  OTel API accepts arbitrary per-call attributes, so tags map straight through;
  pair with `BoundedMetricsSink` for cardinality safety. With no `MeterProvider`
  configured the API is a no-op, so importing never forces an exporter.

- **`TracingMiddleware`** (`tracing/`, ASGI) extracts inbound W3C `traceparent`
  via the global propagator, opens a `SERVER` span per HTTP request, tags it
  with `resilience_kit.request_id` / `…correlation_id` (read from the
  ContextVars) and `http.*` attributes, and marks the span ERROR on a 5xx
  response. It must be placed **inside** `RequestIdMiddleware` so the ids are
  bound when the span opens.

- **Outbound propagation.** `AsyncAPIClient.request` calls
  `tracing.inject_trace_context(headers)` best-effort: the import is guarded so a
  missing `[otel]` extra is swallowed and returns headers unchanged, and with no
  active span injection is a no-op. So an inbound→outbound hop is automatically
  connected when OTel is configured, and costs nothing when it is not.

- **`TracingMiddleware` is opt-in, not auto-wired** into the default FastAPI /
  Django middleware stacks. Auto-inserting it would force the `[otel]` import on
  every adopter (breaking constraint 1). Adopters add it explicitly, just inside
  the request-id middleware. (Deviation from the original #C3 sketch, which said
  "wire into adapter stacks" — recorded here deliberately.)

## Consequences

- A traced inbound request → outbound `AsyncAPIClient` call produces one
  connected trace in any OTLP-capable collector (Jaeger / Tempo), with kit
  metrics under `resilience_kit.*`.
- Zero impact when `[otel]` is not installed: the sink/middleware modules are
  never imported, and the HTTP client's injection no-ops.
- Span naming is `"{method} {path}"`; high-cardinality path templating (e.g.
  `/users/{id}`) is left to the adopter's instrumentation conventions — the kit
  does not parameterise routes.
- Synchronous `Gauge` requires `opentelemetry-api>=1.23`; the extra pins that
  floor.

## Usage

```python
from resilience_kit.middleware.request_id import RequestIdMiddleware
from resilience_kit.tracing import TracingMiddleware

# TracingMiddleware INSIDE RequestIdMiddleware so request_id is bound.
app = RequestIdMiddleware(TracingMiddleware(app))

# Settings: RESILIENCE_METRICS_SINK=otel
```

See `docs/otel-integration.md` for the OTLP-collector exporter recipe.
