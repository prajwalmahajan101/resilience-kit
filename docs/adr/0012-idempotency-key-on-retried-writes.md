# 0012 — Idempotency-Key plumbing on retried unsafe HTTP methods

Status: accepted  ·  Date: 2026-06-29  ·  Milestone: v0.1.1 (Lane B #B2)

## Context

`AsyncAPIClient` wraps every outbound call in `@resilient(service)` —
`circuit_breaker(retry_on_failure(...))`. A POST that times out *after* the
server has begun processing it will be retried, and the retried request can be
processed a second time. For the workloads this kit targets — payments,
disbursements, account creation — that is the canonical double-charge bug.

Outbound payment APIs (Stripe, Razorpay, BHN, …) deduplicate retried requests
via an `Idempotency-Key` header: identical key → the server returns the
original result instead of repeating the side effect. A retry library that does
not plumb this header is a footgun for exactly the workload it is meant to make
safe.

Crucially, the key must be **constant across retry attempts**. The retry loop
lives *inside* `self._send` (the `@resilient`-wrapped `_raw_send`), so a key
generated inside `_raw_send` would differ per attempt and defeat the purpose.

## Decision

`AsyncAPIClient.request()` gains two parameters, resolved **once** in
`request()` (before entering the retry loop) into the `Idempotency-Key` header:

- `idempotency_key: str | None = None` — an explicit value to send.
- `auto_idempotency_key: bool = False` — when `True` and the method is
  POST/PUT/PATCH, generate `uuid.uuid4().hex` once and reuse it for every
  attempt.

Precedence (`_resolve_idempotency_header`): **explicit `idempotency_key` >
a caller-supplied `Idempotency-Key` header (preserved as-is) > auto-generated**.
Auto-generation is scoped to the non-idempotent verbs (`_IDEMPOTENCY_METHODS`);
GET/DELETE are left untouched. A caller-supplied header already survived retries
(the same kwargs dict is reused), so the only genuinely new capabilities are the
explicit argument and auto-generation — but routing all three through one helper
makes the precedence explicit and testable.

The bare `@retry` / `@retry_on_failure` decorators are **not** changed: they
wrap arbitrary callables with no HTTP context, so they cannot generate or place
a key. For those, idempotency remains the caller's responsibility (documented).

`auto_idempotency_key` defaults to `False` so behaviour is unchanged unless
opted into — non-breaking.

## Consequences

- Fintech callers get safe retries on writes with a one-line opt-in
  (`auto_idempotency_key=True`) or by passing their own key.
- The key is fixed before the retry loop, so all attempts — and the breaker's
  view of them — carry the identical header.
- No change for GET-heavy callers or anyone not opting in.
- Scope boundary: the kit only *sends* the header; honouring it is the
  upstream's job. The kit does not itself dedupe.

## Usage

```python
# Auto-generate one key, reused across retries:
await client.post("https://payments.example/charge", json=body,
                  auto_idempotency_key=True)

# Or supply your own (e.g. derived from a domain id):
await client.post("https://payments.example/charge", json=body,
                  idempotency_key=f"charge:{order_id}")
```
