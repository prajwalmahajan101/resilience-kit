# 0002 — Hand-rolled retry, no `tenacity`

Status: accepted  ·  Date: 2026-06-10 (backfilled)  ·  Milestone: M1

## Context

`tenacity` is the de-facto retry library in Python — feature-rich,
well-tested, ergonomic. Adopting it would have saved ~150 LOC and a
test suite.

Two requirements ruled it out:

1. **Composition safety with the circuit breaker.** The kit composes
   retry inside the breaker (ADR 0006). If a caller accidentally swaps
   the order, a retried call could repeatedly retry the
   `ServiceUnavailableError` that an OPEN breaker raises, defeating the
   gate. Retry must hard-code an exclusion: `ServiceUnavailableError` is
   **never** retried, regardless of the caller's `retry_on` tuple.
   Tenacity's `retry_if_exception_type` chain expresses this only via
   caller convention, not as a library invariant — config drift would
   reintroduce the bug.

2. **Sync + async in one decorator with shared state.** The kit's
   `retry()` decorator detects coroutine functions at decoration time
   and dispatches to a sync or async loop that shares the same
   ``_next_delay()`` jitter math and the same `ServiceUnavailableError`
   filter. Tenacity has a separate decorator for each; keeping the math
   identical across both would mean importing tenacity internals.

The retry loop is also small (~150 LOC) and security-relevant. Auditing
our own loop is straightforward; auditing tenacity's full surface every
release is not.

## Decision

Implement retry in `src/resilience_kit/retry/decorator.py` with no
external retry dependency. The module ships:

- `_filter_retry_on()` (line 41) — drops `ServiceUnavailableError` (and
  subclasses) from any caller-supplied `retry_on` tuple as a safety
  net.
- `retry(...)` (line 59) — the public decorator. Sync + async branches
  in one function, total-deadline budget, decorrelated jitter,
  `on_error` callback, `ServiceUnavailableError` re-raised immediately
  on both branches (lines 126, 198).
- `retry_on_failure(service_name)` (line 244) — registry-driven sugar.
- `_next_delay()` (line 320) — jitter math.

No new runtime dependency. `tenacity` is not in `pyproject.toml`.

## Consequences

- Zero retry transitive deps. The kit's `pyproject.toml` core has
  exactly the deps it imports.
- The `ServiceUnavailableError` filter is a library invariant, not a
  caller convention. ADR 0006's composition guarantee survives even if
  someone manually stacks `@retry` outside `@circuit_breaker`.
- We lose tenacity's ecosystem — logging adapters, asyncio cancellation
  hooks, predicate combinators. The kit has its own metrics + audit
  surface; the logging adapters are not load-bearing.
- ~150 LOC and a contract suite to maintain forever. Acceptable: this
  is one of the locked v0.1 APIs (PRD §5.4) and the surface won't grow.

## Usage

Explicit-knobs form:

```python
from resilience_kit import retry

@retry(max_attempts=3, base_delay=1.0, max_delay=10.0, jitter="decorrelated")
async def call_partner(...) -> ...:
    ...
```

Registry-driven form (defaults from `ResilienceSettings.defaults.retry`,
overridden per service):

```python
from resilience_kit import retry_on_failure

@retry_on_failure("partner_api")
async def call_partner(...) -> ...:
    ...
```

`ServiceUnavailableError` is silently dropped from any `retry_on=` you
pass — see `_filter_retry_on()`.
