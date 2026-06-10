# 0011 — Django sync/async bridge

Status: accepted  ·  Date: 2026-06-10  ·  Milestone: M6

## Context

The kit is async-first: `AsyncBreaker`, `AsyncThrottle`, `AsyncCache`,
`RecoveryMonitor`, and the audit dispatcher all assume an asyncio
event loop. Django is sync-first: `AppConfig.ready()` runs
synchronously on process start (and again on autoreload), classic
WSGI views have no running loop, ASGI views have a loop per request,
management commands run sync, and DRF throttle classes are called
synchronously from the request lifecycle.

M6 must therefore translate between those two worlds without:

- starting a private loop inside an existing loop (refused upstream
  in `decorators.py` and `AsyncAPIClient.request_sync`);
- pinning the `RecoveryMonitor` to a per-request loop (it must
  outlive any single request and survive autoreload);
- silently dropping audit events because the dispatcher's queue was
  bound to a closed loop.

## Decision

The Django adapter uses a single dedicated thread + private asyncio
loop for the long-lived background work (the recovery monitor and
the audit dispatcher's queue). Short-lived sync→async calls — DRF
throttles, management commands — use `asyncio.run` per call.

### Long-lived background loop

`ResilienceConfig.ready()` spawns a daemon thread (`name =
"resilience_kit.recovery_monitor"`) that owns a fresh
`asyncio.new_event_loop()` and drives `recovery.monitor` for the
process lifetime. The loop polls a `threading.Event` set by an
`atexit` hook; when the flag flips the loop awaits the audit
dispatcher's `aclose(drain_timeout=5.0)` and `monitor.stop()` *before*
the `_run_loop` finally closes it. Draining must happen on the same
loop the dispatcher's queue was built on; doing it from the `atexit`
hook itself (via `run_coroutine_threadsafe`) would post coroutines to
an already-closed loop.

`daemon=True` means SIGKILL still loses in-flight audit events. The
`FireAndForgetDispatcher` is documented to drop on overflow + on
shutdown crashes, so the trade-off is acceptable; the alternative —
non-daemon thread + signal handlers — would block Django shutdown if
the dispatcher's drain hangs.

Idempotency is enforced by a module-level lock + alive-check so
Django's autoreloader can call `ready()` twice without leaking
threads.

### Short-lived sync→async calls

DRF throttle classes (`IPThrottle`, `UserTierThrottle`,
`EndpointThrottle`, `BurstThrottle`, `AuthThrottle`) implement
`allow_request` synchronously and call
`asyncio.run(get_throttle().check(...))`. The kit's `decorators.py`
refuses to nest loops, so the throttle path works only outside a
running loop — i.e. from a sync DRF view or a management command.
ASGI views call DRF throttles from a running loop, which would
collide with `asyncio.run`; the adapter documents this constraint
and recommends the FastAPI `rate_limit` dependency for ASGI workloads
that need throttling.

The management commands (`resilience_status`, `resilience_reset`) are
inherently short-lived, so the per-call `asyncio.run` cost is
negligible.

### Things this ADR deliberately does *not* do

- **Reuse the background thread's loop for DRF throttle calls.**
  `asyncio.run_coroutine_threadsafe` would cross-thread the throttle's
  per-request state and tie request latency to the daemon's wake
  cadence. Easier to pay the `asyncio.run` overhead per call and keep
  the threads independent.
- **Use `asgiref.sync.async_to_sync`.** `asgiref` is a Django
  dependency, so the import would be free; but its event-loop reuse
  pattern (cached thread-local) hits the same "Event bound to a
  different loop" class of failure the recovery-monitor fix in
  `fix(recovery): rebind monitor stop-event on every start` addressed.
  `asyncio.run` is simpler and the latency overhead is sub-millisecond.

### Throttle deny semantics — raise, do not return False

`_KitThrottle.allow_request` raises `RateLimitError` instead of
returning `False`. Returning `False` routes the deny through DRF's
own `Throttled` exception, which carries a different envelope and
loses the kit's `limit / remaining / reset_at` fields. Raising routes
through the DRF `EXCEPTION_HANDLER` (the adapter's `handle()`), which
emits the LLD §11 envelope and the canonical `X-RateLimit-*` headers.

## Consequences

- Django + WSGI: the kit works fully — middleware, throttles, fields,
  HTTP client, monitor, audit. Adopters install `INSTALLED_APPS +=
  ["resilience_kit.adapters.django"]` and the daemon starts on first
  worker boot.
- Django + ASGI: middleware + fields work natively; throttles work
  only from sync code paths. ASGI projects that need request-time
  throttling should consider the FastAPI adapter.
- Audit drain on SIGKILL is best-effort: in-flight events are lost.
  Production deployments should run workers behind a reverse proxy
  that uses SIGTERM for graceful shutdown (Gunicorn / Uvicorn / Hypercorn
  defaults).
- The recovery-monitor `stop()` event was rebound at `start()` time
  in `fix(recovery): rebind monitor stop-event on every start` as a
  shared M5 + M6 pre-flight. Without it the daemon thread cannot be
  restarted on Django's autoreloader.

## Usage

```python
# settings.py
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "resilience_kit.adapters.django",
    "your_app",
]

MIDDLEWARE = [
    "resilience_kit.adapters.django.middleware.ExceptionLoggingMiddleware",
    "resilience_kit.adapters.django.middleware.SecurityHeadersMiddleware",
    "resilience_kit.adapters.django.middleware.RateLimitHeadersMiddleware",
    "resilience_kit.adapters.django.middleware.RequestIdMiddleware",
    "django.middleware.common.CommonMiddleware",
    ...,
]

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "resilience_kit.adapters.django.exception_handler.handle",
}

RESILIENCE = {
    "services": {
        "partner": {"retry": {"max_attempts": 4}},
    },
}

RESILIENCE_THROTTLE_RATES = {
    "ip": "60/min",
    "auth": "5/min",
}
```

Operational commands:

```bash
./manage.py resilience_status
./manage.py resilience_status --json
./manage.py resilience_reset partner
./manage.py resilience_reset --all
```
