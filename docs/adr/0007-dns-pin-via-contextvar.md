# 0007 — DNS pin via ContextVar

Status: accepted  ·  Date: 2026-06-09  ·  Milestone: M3

## Context

The SSRF guard (`resilience_kit.ssrf.guard.resolve_and_validate`)
resolves a hostname and rejects URLs whose resolved IPs are non-public.
But the validate step and the *connect* step are separated by an async
boundary — the canonical DNS-rebinding TOCTOU: a malicious zone returns
a public IP at validate time and a private one at connect time. The
SSRF check passes; the actual connect goes to localhost.

The kit needs a mechanism that carries the validator's resolved IP set
through the validate → connect boundary and forces the connect to use
**only** those IPs.

Constraints:

- The transport is `httpx` (LLD §1, pyproject `[http]` extra).
- The kit is async-first; pinning must survive `await` boundaries
  inside a task and be isolated across concurrent tasks (LLD §9).
- The pin must not leak to the next request on the same task; cleanup
  must be deterministic.
- Adapters land later (M5 / M6); the primitive must be framework-
  agnostic.

## Decision

Use a `contextvars.ContextVar[dict[str, set[str]] | None]` named
`pinned_dns` to carry the host → IP-set mapping. A
`@contextmanager pinned(host_to_ips)` helper sets the var with token
restore on exit. A custom transport — `PinnedHTTPTransport`,
subclassing `httpx.AsyncHTTPTransport` — reads the ContextVar on every
`handle_async_request`, rewrites the request URL host to one of the
pinned IPs, and sets the `Host` header + `extensions["sni_hostname"]`
back to the original hostname so TLS verification continues to work.

`AsyncAPIClient.request` is the single composition point: it calls
`resolve_and_validate`, installs the pin via `pinned(...)`, dispatches
through the `@resilient(service)` decorator, and the transport rewrite
happens at the bottom of the stack.

## Consequences

- One task cannot leak its pin to another (ContextVar semantics) — fits
  the kit's async-first model.
- The rewrite happens at the transport layer, so it survives any
  middleware / interceptor an adapter might add on top.
- Cert verification is unchanged because SNI + `Host` header carry the
  original hostname.
- Tradeoff: every `AsyncAPIClient.request` validates and resolves on
  the hot path. The DNS cache lives in the transport (`httpx`'s
  default) — the SSRF guard's own resolution is a second `getaddrinfo`
  call. Acceptable for correctness; revisit if it shows up in a
  profile.
- Locked-in dep: `httpx>=0.27,<0.29` — the transport extension point
  has churned across minor versions; widening the range requires the
  integration test in `tests/integration/test_dns_rebinding.py` to
  still pass.

## Usage

```python
from resilience_kit import AsyncAPIClient

client = AsyncAPIClient(service="partner")
resp = await client.get("https://partner.example/v1/x")
# resolve_and_validate → pinned(...) → @resilient(partner) → httpx
```

To pin manually outside the client (rare — usually only tests or
ad-hoc scripts):

```python
from resilience_kit.http_client import pinned, pinned_httpx_client

with pinned({"partner.example": {"1.2.3.4"}}):
    async with pinned_httpx_client() as c:
        await c.get("https://partner.example/")
```
