# OpenTelemetry integration

The `[otel]` extra adds an OpenTelemetry metrics sink and W3C trace-context
propagation. See [ADR-0016](./adr/0016-trace-context-propagation.md) for the
design.

```bash
pip install "resilience-kit[otel]"
```

## Metrics → OTel

Select the sink:

```bash
RESILIENCE_METRICS_SINK=otel
# recommended alongside an exporter:
RESILIENCE_METRICS_CARDINALITY_BUDGET=100
```

Kit metrics are emitted under the `resilience_kit.` meter namespace
(`resilience_kit.breaker.open`, `resilience_kit.retry.exhausted`,
`resilience_kit.throttle.fail_closed`, …). They flow wherever your configured
`MeterProvider` exports — with none configured the OTel API is a no-op.

## Tracing

`TracingMiddleware` opens a `SERVER` span per request and tags it with the kit's
`request_id` / `correlation_id`. Place it **inside** `RequestIdMiddleware` so
those ids are bound when the span starts:

```python
from resilience_kit.middleware.request_id import RequestIdMiddleware
from resilience_kit.tracing import TracingMiddleware

app = RequestIdMiddleware(TracingMiddleware(app))
```

Outbound `AsyncAPIClient` calls automatically inject the active span's W3C
`traceparent`, so a downstream service continues the same trace — no extra
wiring needed.

## Wiring an OTLP exporter (Jaeger / Tempo)

```python
from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

resource = Resource.create({"service.name": "my-service"})

tp = TracerProvider(resource=resource)
tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # OTEL_EXPORTER_OTLP_ENDPOINT
trace.set_tracer_provider(tp)

mp = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(mp)
```

> The OTLP exporter packages (`opentelemetry-exporter-otlp-proto-http`) are
> **not** pulled in by `[otel]` — install the exporter that matches your
> collector. The kit only depends on `opentelemetry-api` / `-sdk`.

With the providers set, a request through `TracingMiddleware` → `AsyncAPIClient`
produces a connected trace in your collector and kit metrics in your metrics
backend.
