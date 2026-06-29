# 0006 — Outer breaker, inner retry

Status: accepted  ·  Date: 2026-06-10 (backfilled)  ·  Milestone: M1

## Context

A retry decorator and a circuit-breaker decorator can be composed two
ways:

1. **Outer breaker, inner retry** — `circuit_breaker(retry(func))`.
   The breaker gate is checked first. If `OPEN`, the breaker raises
   `ServiceUnavailableError` immediately and the inner retry loop never
   runs. If `CLOSED`, retry attempts proceed; transient failures count
   toward the breaker's failure window.
2. **Outer retry, inner breaker** — `retry(circuit_breaker(func))`.
   The retry loop wraps the breaker. The first attempt opens the
   breaker; the retry loop calls the breaker again and gets
   `ServiceUnavailableError`; the retry loop then retries
   `ServiceUnavailableError` and keeps hammering an OPEN breaker.

(2) defeats the breaker's purpose: the system retries the very signal
that says "stop trying." (1) lets the breaker do its job — gate first,
then retry only what should be retried.

The kit must compose this for callers via `@resilient(name)` and must
also protect against callers who manually stack the two decorators in
the wrong order.

## Decision

`@resilient(name)` always composes as
`circuit_breaker(retry_on_failure(func))` — outer breaker, inner retry.
See `src/resilience_kit/decorators.py:107-128`:

```python
def resilient(service_name: str) -> ...:
    def decorator(func):
        retried = retry_on_failure(service_name)(func)
        return circuit_breaker(service_name)(retried)
    return decorator
```

As a safety net for hand-stacked decorators, the retry loop hard-codes
`ServiceUnavailableError` in its "never retry" list:
`_filter_retry_on()` drops it from any caller-supplied `retry_on`
(`src/resilience_kit/retry/decorator.py:41-56`), and the loop re-raises
it immediately on both sync and async branches (lines 126 and 198).
Even an inverted stack cannot retry past an OPEN breaker.

## Decision — default excluded exceptions (#B3)

A breaker counts failures to detect an unhealthy *downstream service*. But a
caller raising `ValueError` for bad input, or a `KeyError`/`TypeError` from a
programmer mistake, says nothing about the downstream's health. Counting these
toward the failure window is a false-positive open that drops legitimate
traffic.

`BreakerConfig.excluded_exceptions` therefore defaults to a non-empty set
(`circuit_breaker/base.py:DEFAULT_EXCLUDED_EXCEPTIONS`):

```python
(ValueError, TypeError, KeyError, AttributeError, AssertionError)
```

These are re-raised without recording a failure. This is opinionated —
operators whose conventions differ override it per service via the
`excluded_exceptions` override, and the registry honours that override
(`registry.py`), falling back to the default set only when none is supplied.

Note this is orthogonal to retryability: `ExternalServiceError` (upstream
returned non-success) is *not* excluded — it is the canonical breaker-failure
signal even though it is not retried.

## Consequences

- An OPEN breaker short-circuits immediately. No retry log noise, no
  exponential-backoff sleep, no metric inflation.
- Cascading failures don't amplify — the breaker's whole job survives.
- Manual decorator stacks must follow the documented order
  (`@circuit_breaker` outermost, `@retry` inside). The safety-net
  filter catches mistakes but the call still doesn't get the retry
  semantics the caller intended; metrics + audit log the
  `ServiceUnavailableError` cleanly.
- The retry decorator can never be told to retry on
  `ServiceUnavailableError` — even if a caller explicitly puts it in
  `retry_on=(...)`. Documented in `retry()`'s docstring at line 77.

## Usage

The standard outbound wrap:

```python
from resilience_kit import resilient

@resilient("partner_api")
async def get_balance(account_id: str) -> Decimal:
    response = await http_client.get(f"/accounts/{account_id}/balance")
    return Decimal(response.json()["balance"])
```

Manual stack (equivalent — keep this order):

```python
from resilience_kit import circuit_breaker, retry_on_failure

@circuit_breaker("partner_api")   # outer
@retry_on_failure("partner_api")  # inner
async def get_balance(account_id: str) -> Decimal:
    ...
```

Inverted stack — **don't do this**, but the safety net still holds:

```python
@retry_on_failure("partner_api")   # outer — WRONG
@circuit_breaker("partner_api")    # inner — WRONG
async def get_balance(...):
    ...
# An OPEN breaker raises ServiceUnavailableError; the outer retry
# loop will not retry it because retry/_filter_retry_on drops it.
```
