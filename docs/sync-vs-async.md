# Sync vs. async — when the kit drives a private loop

The kit is async-first. Adapters that live in sync frameworks
(Django + WSGI, sync DRF, management commands) need a deterministic
story for how sync code reaches async primitives. This page
documents the rules. ADR 0011 is the longer form.

## The three patterns

| Pattern | Used by | What it does | When it refuses |
|---|---|---|---|
| **Background daemon thread + private loop** | `resilience_kit.adapters.django.apps` | Spawns one daemon thread, runs `asyncio.new_event_loop()`, drives `recovery.monitor` for the process lifetime. Drains the audit dispatcher on graceful exit. | Never (idempotent). Reused across Django autoreload by the alive-check. |
| **`asyncio.run` per call** | DRF throttle classes; management commands | Sync code spins a private loop for one coroutine, runs it, closes it. Fine for short-lived calls (sub-millisecond per spin). | Refuses when called from a running loop — the kit's `decorators.py` enforces this. |
| **`request_sync` on `AsyncAPIClient`** | Sync Django views that need outbound HTTP | Detects whether a loop is already running; if not, drives a private one. If a loop *is* running it raises `RuntimeError` rather than nesting. | Refuses inside a running loop. ASGI views must use `await client.request(...)` instead. |

## What this means in practice

### Django + WSGI (the common case)

Everything works out of the box. The daemon thread owns the monitor;
DRF throttles use `asyncio.run` (no ambient loop, so no conflict);
sync views call `AsyncAPIClient.request_sync` and the helper drives
its own loop.

### Django + ASGI

Middleware and the `EncryptedCharField` work natively. **DRF
throttles do not work from ASGI views** because the ASGI view runs
inside a loop and the throttle's `asyncio.run` collides with it. Two
ways out:

1. If you only need throttling, move that route to a sync view —
   Django supports per-view sync/async mixing.
2. If the project is async-heavy, switch the throttle layer to the
   FastAPI adapter's `rate_limit` dependency, which is async-native.

### Management commands

`./manage.py resilience_status` and `./manage.py resilience_reset`
run sync. Both wrap `asyncio.run(...)` around their kit calls. There
is no ambient loop in a management command, so the pattern is safe.

## Why not `async_to_sync` from asgiref

`asgiref.sync.async_to_sync` is tempting because it ships with
Django, but it caches a thread-local event loop. That cache is the
same class of bug `fix(recovery): rebind monitor stop-event on every
start` chased down for `RecoveryMonitor`: a coroutine built on one
loop, awaited on another, raises
`RuntimeError: <Event> is bound to a different event loop`. The
kit's `asyncio.run` path is one-shot and avoids the bug surface.

## Why not block the request to await the daemon thread's loop

`run_coroutine_threadsafe` would let a sync DRF throttle call hop
onto the daemon's loop and await the result. Two reasons we do not:

1. The daemon's loop is driving the recovery monitor on a fixed
   half-second wake cadence. Cross-thread scheduling would inject
   request-bound work into that schedule and couple p99 latency to
   the monitor's `await asyncio.sleep(0.5)` cycle.
2. Cross-thread state is harder to reason about than per-call
   isolation. `asyncio.run` rebuilds + tears down everything; the
   kit's testing helpers also depend on per-call isolation to reset
   singletons cleanly.

## Quick rules

- **Background work that must outlive a request** → daemon thread +
  private loop (`adapters/django/apps.py`).
- **Sync code reaching a single async primitive once** → `asyncio.run`.
- **Sync HTTP outbound** → `AsyncAPIClient.request_sync` (refuses
  inside a running loop, otherwise drives its own).
- **Async code reaching a sync helper** → use the sync helper
  directly; `await` is unnecessary and adds nothing.
