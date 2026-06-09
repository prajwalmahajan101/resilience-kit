# 0005 — Fire-and-forget audit dispatch

Status: accepted  ·  Date: 2026-06-09  ·  Milestone: M4

## Context

The audit (`api_log`) subsystem captures every inbound + outbound RPC
into structured records that downstream tooling (security review,
forensics, debugging, compliance) consumes. The kit needs to record
those records reliably **without** charging the request hot path for
storage latency: if the audit backend is slow / down / network-
partitioned, request handlers must not wait on it.

The boilerplates the kit replaces wrote audit rows synchronously inside
the request and paid for that decision every time the audit DB hiccupped.

## Decision

Decorators (`@log_inbound`, `@log_outbound`) build an `AuditEvent` and
hand it to the configured `AuditDispatcher` via `submit()` — a non-
blocking call. A `FireAndForgetDispatcher` owns:

1. A bounded `asyncio.Queue` (default 10,000 events) — full queue
   *drops the newest event* and bumps `audit.dropped` so the loss is
   observable.
2. A background asyncio worker spawned in
   `contextvars.copy_context()` so the request's ContextVars do not
   leak into other requests' flushes.
3. A batched flush: up to `batch_max` (100) events per
   `AuditBackend.write_many`, with at most `batch_interval_ms` (50ms)
   wait between flushes.
4. Backend retry x3 with capped exponential backoff + jitter on
   transient failure; on exhausted retries, the batch falls back to a
   `StdlibLoggingAuditBackend` and bumps `audit.write_failed` so the
   loss is observable.
5. Graceful drain on shutdown via `aclose(drain_timeout=5.0)` — the
   adapter lifespan calls this so pending events flush before the
   process exits; remaining events count toward `audit.dropped`.

## Consequences

- Request hot path is **never** blocked by audit backend latency.
- Loss is observable, not silent. Every drop / failed write increments
  a metric so operators see degradation.
- Per-batch retry plus stdlib_logging fallback means the audit pipeline
  has the same fail-open posture as the rest of the kit: a Postgres
  outage logs to stdout rather than failing requests.
- Tradeoff: events are not ordered relative to one another (multiple
  worker batches may flush concurrently if multiple dispatchers are
  configured). Audit is per-request, not a totally-ordered log.
- Tradeoff: under sustained overload the queue fills and newest events
  drop. The alternative — drop-oldest — risks losing the *first* event
  that triggered a downstream cascade, which is usually the one the
  operator wants. (`OverflowPolicy.DROP_OLDEST` is opt-in for callers
  who want the inverse trade.)

## Usage

```python
from resilience_kit import log_outbound

@log_outbound("partner", method="GET", path="/v1/x")
async def fetch_partner(*, partner_id: str) -> dict[str, str]:
    ...
```

The dispatcher is built lazily from settings on first use:

```bash
RESILIENCE_AUDIT__SINK=postgres
RESILIENCE_AUDIT__SANITIZER=default
RESILIENCE_AUDIT__QUEUE_SIZE=10000
RESILIENCE_AUDIT__BATCH_MAX=100
RESILIENCE_AUDIT__BATCH_INTERVAL_MS=50
```

Tests use the `InlineDispatcher` (sanitises + writes synchronously,
backend errors surface):

```python
from resilience_kit.audit import set_dispatcher
from resilience_kit.audit.dispatch import InlineDispatcher

set_dispatcher(InlineDispatcher(backend))
```
