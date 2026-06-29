# 0013 — Throttle fail-mode under a Redis outage

Status: accepted  ·  Date: 2026-06-29  ·  Milestone: v0.1.1 (Lane B #B8)

## Context

Every Redis-backed primitive in the kit (cache, breaker, throttle, audit)
follows the same degradation shape: on a `RedisError`, mark degraded, fall
back to an in-memory implementation, and let the recovery monitor restore the
primary path (the kit's "fail-open on resilience-infra failure" rule).

For cache, breaker, and audit this is correct — a dead Valkey must not block
all requests. **For a distributed throttle it is subtly wrong.** The in-memory
fallback is *per pod*. A global `100/min` limit enforced across 8 pods becomes,
during a Redis outage, `100/min` *per pod* — `800/min` for the fleet. For a
payment API with a hard upstream rate limit, that multiplicative blast radius
can cause a cascade failure precisely when the system is already degraded.

The original behaviour (always fail-open to in-memory) was documented only in
passing in LLD §6 and gave operators no way to opt into the safer behaviour.

## Decision

`RedisAsyncThrottle` takes a `fail_mode: Literal["open", "closed"]`, defaulting
to `"open"`, surfaced through settings as `defaults.throttle.fail_mode`.

- **`"open"`** (default) — preserve current behaviour: degrade to the per-pod
  `InMemoryAsyncThrottle`. Ergonomic; correct when approximate local limiting
  during an outage is acceptable.
- **`"closed"`** — while degraded, `check()` returns
  `ThrottleDecision(allowed=False, remaining=0, …)` immediately and emits
  `metrics.incr("throttle.fail_closed")`. No request is admitted until Redis
  recovers. Correct for hard upstream limits.

Both degraded entry points (the pre-call "already degraded" short-circuit and
the in-call `RedisError` catch) route through one `_degraded_decision()` helper
so the two modes can never diverge.

The default stays `"open"` so this is a non-breaking change; fintech / hard-limit
operators flip a single setting.

`ThrottleDecision` is locked at v0.1 (LLD §2) and was **not** extended with a
`reason` field — the fail-closed signal is carried by the `throttle.fail_closed`
metric instead, keeping the locked decision shape intact.

## Consequences

- Default deployments are unchanged.
- Operators with hard upstream limits get a one-line opt-in to fail-closed and a
  dedicated metric to alert on.
- The per-pod multiplier is now documented loudly (README + LLD §6) rather than
  whispered, so the fail-open trade-off is an informed choice.
- A future enhancement could push a shared degraded counter (e.g. a local token
  budget = global ÷ replica count) for a middle ground; out of scope here.

## Usage

```python
# Settings (env): RESILIENCE_DEFAULTS__THROTTLE__FAIL_MODE=closed
# or programmatically:
from resilience_kit.throttle.redis_impl import RedisAsyncThrottle

throttle = RedisAsyncThrottle(redis_client=client, fail_mode="closed")
```

During a Redis outage, a `"closed"` throttle denies with `allowed=False` and
increments `throttle.fail_closed`; an `"open"` throttle serves from the per-pod
in-memory window and increments `throttle.degraded`.
