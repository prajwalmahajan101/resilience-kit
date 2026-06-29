# Sentry integration

The `[sentry]` extra ships a `SentryMetricsSink` that leaves a Sentry breadcrumb
for the kit's significant failure signals, so a captured exception carries the
trail of `breaker.open` / `retry.exhausted` / `throttle.fail_closed` events that
preceded it.

```bash
pip install "resilience-kit[sentry]" "sentry-sdk[fastapi]"   # or sentry-sdk[django]
```

## Wire the sink

```python
import sentry_sdk
sentry_sdk.init(dsn="https://...@sentry.io/...", traces_sample_rate=0.1)
```

```bash
RESILIENCE_METRICS_SINK=sentry
# wrap with the cardinality guard as usual:
RESILIENCE_METRICS_CARDINALITY_BUDGET=100
```

Each breadcrumb's `data` carries the kit's `request_id` / `correlation_id`
ContextVars plus the metric tags. The breadcrumbed set defaults to the headline
failure/degradation metrics (`breaker.open`, `breaker.degraded`,
`retry.exhausted`, `throttle.fail_closed`, `throttle.degraded`, `cache.degraded`,
`audit.write_failed`, `audit.dropped`); construct `SentryMetricsSink(breadcrumb_metrics=...)`
to customise.

The sink is **terminal** — it does not also forward to a counter backend. If you
want Prometheus/OTel counters *and* Sentry breadcrumbs, run a counter sink as
`metrics_sink` and add breadcrumbs through Sentry's own integrations, or compose
your own sink.

## request_id as a Sentry tag (middleware, not the sink)

Tagging every event with the request id belongs in request middleware, where the
ContextVar is bound — not in a metrics sink. With the kit's `RequestIdMiddleware`
seeding the ContextVar, add a thin tagging layer inside it:

```python
import sentry_sdk
from resilience_kit.context import request_id, correlation_id

class SentryTagMiddleware:
    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope_ = sentry_sdk.get_current_scope()
            rid = request_id.get()
            if rid:
                scope_.set_tag("request_id", rid)
            cid = correlation_id.get()
            if cid:
                scope_.set_tag("correlation_id", cid)
        await self._app(scope, receive, send)

# Place INSIDE RequestIdMiddleware so the ContextVars are already bound:
app = RequestIdMiddleware(SentryTagMiddleware(app))
```

## FastAPI / Django

Use Sentry's own framework integrations for request capture
(`sentry_sdk.integrations.fastapi.FastApiIntegration`,
`sentry_sdk.integrations.django.DjangoIntegration`); the kit's sink only adds the
resilience-event breadcrumbs on top.
