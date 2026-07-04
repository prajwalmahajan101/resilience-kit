# 0017 — Single shared Redis client, explicitly closed

Status: accepted  ·  Date: 2026-07-04  ·  Milestone: v0.2.0 (Lane D #D1)

## Context

Every Redis-backed subsystem — cache, circuit breaker, throttle — needs an
`redis.asyncio.Redis`. Through v0.1 each provider built its own on first use:

```python
# cache/provider.py, circuit_breaker/provider.py, throttle/provider.py
client = Redis.from_url(settings.redis_url)
```

Two problems followed from that:

1. **Three pools where one would do.** A process that used all three subsystems
   ran three independent connection pools against the same server, tripling idle
   connections and file descriptors for no benefit.
2. **Leak on re-registration.** Nothing ever called `aclose()`. `reset_*` test
   hooks and adapter shutdown dropped the *impl* but never closed the underlying
   client. Registering a breaker for a new service, or re-running the provider
   after a `reset`, orphaned the previous client — its pool stayed open until GC,
   which for an async client is not guaranteed to close sockets cleanly.

The impls already accept an injected `redis_client` (tests pass stubs), so the
client's lifecycle was never the impl's concern — only the providers minted them.

## Decision

Centralise client ownership in a new `resilience_kit._redis` module:

- **`get_redis_client(url) -> Redis`** — memoises one client per URL in a
  process-wide dict under a `threading.Lock`. All three providers call it instead
  of `Redis.from_url`, so subsystems sharing a URL share one pool. The `redis`
  import stays lazy (guarded by the `[redis]` extra) — importing `_redis` does not
  require `redis` installed.
- **`aclose_redis_clients()`** (async) — closes every client and clears the cache.
  Wired into the teardown paths that already own an event loop:
  - FastAPI `resilience_lifespan` exit (after the monitor stops);
  - the Django adapter's daemon-loop `_drive_monitor` shutdown;
  - `testing.reset.reset_all_singletons_async`.
- **`reset_redis_clients()`** (sync) — drops references without awaiting, for the
  sync `reset_all_singletons` test hook. Test suites own their Redis fixtures
  (fakeredis / testcontainers) and tear connections down themselves, so a
  reference drop is enough to force a fresh client next build; the async variant
  is the one that truly closes.

Sharing one client is safe during a Redis outage: each impl degrades to its own
in-memory fallback and re-probes the *same* client via `ping`, which redis-py
auto-reconnects — there is no per-subsystem connection state to keep separate.

## Consequences

- One pool per URL instead of three; fewer idle connections and FDs.
- Clients are closed deterministically on adapter shutdown and async test reset,
  not left to GC — no orphaned pools across re-registration.
- Providers no longer import `redis.asyncio` directly; the lazy import lives in
  one place.
- The sync `reset_all_singletons` cannot truly close async clients (no loop);
  async harnesses must use `reset_all_singletons_async` for a real close. This is
  a deliberate, documented split rather than a hidden best-effort.
- A future multi-URL deployment (read replica + primary) already works — the
  cache is keyed by URL.

## Usage

```python
from resilience_kit._redis import get_redis_client, aclose_redis_clients

client = get_redis_client(settings.redis_url)   # shared, built once
...
await aclose_redis_clients()                     # on shutdown

# Tests:
from resilience_kit.testing import reset_all_singletons_async
await reset_all_singletons_async()               # resets + closes clients
```
