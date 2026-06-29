# resilience-kit — Full Coverage Map & Go Porting Blueprint

> **What this doc is.** Three things in one place:
>
> 1. **Part A — Coverage map.** Everything `resilience-kit` (Python) actually
>    ships: every module, primitive, protocol, and cross-cutting concern.
> 2. **Part B — Go interop verdict.** Can a Go service *reuse* this Python kit
>    via an SDK / plugin / FFI / sidecar? Short answer: **not for the
>    in-process primitives** — and the reasons are structural, not a tooling
>    gap.
> 3. **Part C — `go-resilience-kit` blueprint.** A module-by-module plan to
>    re-implement the kit natively in Go, **sharing the same Valkey state** as
>    the Python kit (same Lua scripts, same key schemas) so the two languages
>    interoperate at the data layer even though the code does not.
>
> Companion to [PRD.md](./PRD.md) (what & why), [LLD.md](./LLD.md) (internal
> contracts), and [ROADMAP.md](./ROADMAP.md) (when). Where this doc states a
> contract (key schema, Lua semantics, exception mapping), the LLD is the
> source of truth — cross-references are inline.

---

## Part A — What the kit covers

The kit is a **single PyPI distribution** (`resilience-kit`) with a pure-Python
core and optional backends/adapters behind pip extras. Layering is enforced
L0→L4 by import-linter ([LLD §1](./LLD.md#1-module-boundaries)); a lower layer
never imports a higher one.

### A.1 Core resilience primitives

| Primitive | Module | What it does | Backends |
|---|---|---|---|
| **Retry** | `retry/` | `@retry`, `@retry_on_failure(service)` — exponential backoff with `none`/`full`/**`decorrelated`** jitter. Handrolled (not Tenacity), async-native with sync wrapper. | pure-Python |
| **Circuit breaker** | `circuit_breaker/` | `@circuit_breaker(service)` — CLOSED→OPEN→HALF_OPEN state machine. `fail_max`, `reset_timeout`, `success_threshold`. | `memory`, `redis` (atomic Lua), `pybreaker` |
| **Throttle / rate-limit** | `throttle/` | Token-bucket + scopes (`ip`/`endpoint`/`user_tier`/`global`/`burst`/`auth`). Returns `ThrottleDecision{allowed, remaining, reset_after, limit}`. | `memory`, `redis` (atomic Lua) |
| **Cache** | `cache/` | `AsyncCache` — `get/set/add(NX)/incr/delete`, TTL-aware. Backs throttle + blacklist. | `memory`, `redis` |
| **Composite** | `decorators.py` | `@resilient(service)` = **outer breaker over inner retry** (locked order; `ServiceUnavailableError` filtered from `retry_on` as a safety net). | — |
| **Registry** | `registry.py` | Per-service config + defaults overlay; `get_breaker(name)`, `health_snapshot()` for `/readyz`. | — |
| **Recovery monitor** | `recovery.py` | Process-wide singleton task. Re-probes degraded backends with capped exponential backoff; resets provider cache on recovery. Django runs it in a daemon thread + private loop. | — |

**Key behavioral invariants** (these are the contract, [LLD §4/§8/§9](./LLD.md)):

- **Outer breaker, inner retry** — an OPEN breaker short-circuits *before*
  retry can hammer a dead upstream.
- **Fail-open on infra failure** — a dead Valkey degrades throttle/cache/breaker
  to in-memory and emits a metric; it never blocks all traffic. Recovery monitor
  restores the real backend.
- **Cancellation is not failure** — `asyncio.CancelledError` propagates
  unchanged and does not trip the breaker.

### A.2 I/O & security

| Module | Surface | Notes |
|---|---|---|
| **SSRF guard** | `ssrf/guard.py` | `resolve_and_validate(url)`, `assert_allowed_url(url)`, `assert_public_url`. Resolves DNS, denies RFC1918 / loopback / link-local / reserved CIDRs, enforces host allow-list. |
| **DNS-pinned HTTP client** | `http_client/` | `AsyncAPIClient` composes ssrf → breaker → retry → audit. Pins resolved IPs in a `ContextVar` and feeds a custom httpx resolver so connect uses **only** validated IPs — closes the validate→connect **TOCTOU** ([LLD §5](./LLD.md#5-dns-pinned-http-request)). Bearer/basic/HMAC auth helpers. |
| **Field crypto** | `crypto/fernet.py` | `FernetCipher.encrypt/decrypt` (Fernet/AES). Env-guard refuses to start without a key outside dev/test ([ADR 0008](./adr/0008-fernet-env-guard.md)). |

### A.3 Audit / api_log

`@log_inbound` / `@log_outbound` decorators → `Sanitizer` (field redaction) →
**fire-and-forget bounded queue** → batched `AuditBackend.write_many`
([LLD §7](./LLD.md#7-audit-dispatch--fire-and-forget)).

- Non-blocking decorator path; **lossy-but-observable** under overload
  (drops increment `audit.dropped`); graceful drain on shutdown.
- `AuditEvent` carries `request_id`, direction, service, method, target,
  status, timing, **sanitized** payload/response, error_code.
- Backends: `noop`, `stdlib_logging`, `postgres` (asyncpg), `django_orm`.

### A.4 Observability, lifecycle, middleware

| Module | Provides |
|---|---|
| `metrics.py` | `MetricsSink` protocol (RED metrics) — `incr/timing/gauge`. No Prometheus dep; callers wire their own sink. |
| `health.py` | `/readyz` aggregator helpers, `HealthAggregate`/`HealthStatus`. |
| `middleware/` | Framework-agnostic ASGI/WSGI factories: `request_id`, `body_limit`, `security_headers`, `selective_cors`, `rate_limit_headers`, `exception_logging`. |
| `context.py` | `request_id`, `correlation_id`, `pinned_dns` **ContextVars** — the cross-cutting bus (never threadlocals/globals). |
| `tasks/`, `dispatch/` | Lightweight fire-and-forget task queue scaffold (no Celery dep). |

### A.5 Pluggability model (3 mechanisms)

1. **Pip extras** — `[redis]`, `[pybreaker]`, `[http]`, `[requests]`,
   `[crypto]`, `[audit-postgres]`, `[django]`, `[fastapi]`, `[all]`. Importing a
   backend without its extra raises `MissingExtraError` with the exact `pip
   install` hint — never a deep `ModuleNotFoundError`.
2. **Protocols, not ABCs** — every swappable subsystem is a `typing.Protocol`
   ([ADR 0001](./adr/0001-protocol-not-abc.md)). Concrete impls are duck-typed.
3. **Entry-point discovery** — 7 entry-point groups
   (`resilience_kit.{cache,breaker,throttle,audit}_backends`,
   `audit_sanitizers`, `metrics_sinks`, `settings_sources`). Third parties ship
   a backend without forking. Resolution order: explicit instance → importable
   string (`pkg.mod:Class`) → entry-point name → builtin name → `UnknownBackendError`
   with the available list ([LLD §3](./LLD.md#3-provider-resolution-chain)).

### A.6 Config, exceptions, adapters

- **Settings** — one pydantic-v2 `ResilienceSettings`, env-driven with
  `RESILIENCE_` prefix and `__` nesting ([LLD §10](./LLD.md#10-settings-schema)).
- **Exception → HTTP map** — locked table ([LLD §11](./LLD.md#11-exception--http-mapping)):
  `ValidationError`→400, `RateLimitError`→429 (+`Retry-After`),
  `ServiceUnavailableError`→503 (+`Retry-After`), `ExternalTimeoutError`→504,
  `ExternalServiceError`→502, `DecryptionError`/`RepositoryError`→500,
  `MissingExtraError`→refuse-to-start.
- **Adapters** (≲500 LOC pure glue, zero business logic):
  - **FastAPI** — `lifespan` (recovery monitor + `/readyz`), `rate_limit`
    dependency, exception handlers, `EncryptedString` SQLAlchemy TypeDecorator.
  - **Django** — `AppConfig`, DRF throttle classes, exception handler,
    `EncryptedCharField`, `resilience_reset` / `resilience_status` management
    commands. Sync↔async bridge via daemon-thread loop
    ([ADR 0011](./adr/0011-django-sync-async-bridge.md)).

### A.7 Testing surface

`testing/` ships `reset_all_singletons()`, `FakeClock`, fakes. The **contract
suite** (`tests/contract/`) is one file per primitive, parametrized over
`memory`/`redis`/`pybreaker` — the same assertions prove every backend. This
suite is the executable spec a Go port must also satisfy (see Part C.6).

---

## Part B — Can Go reuse this kit directly?

**Verdict: No — not for the in-process primitives. Yes — for the shared-state
contract.** The split is the whole point, so be precise about it.

### B.1 Why the in-process primitives can't be "plugged into" Go

The kit's value is **in-process control flow**: a decorator wraps your function
call, checks breaker state, retries with backoff, all on the calling
goroutine/thread with microsecond overhead ([LLD §13](./LLD.md#13-performance-budget-informational)
targets `@retry` < 5µs, `MemoryBreaker.call` < 10µs). Every interop option
breaks that:

| Option | Why it fails for resilience primitives |
|---|---|
| **CGo + CPython embed** (`gopy`, `go-python`, `cpy3`) | Drags a full CPython interpreter + the **GIL** into your Go binary. asyncio event loop has no clean mapping to goroutines. You'd serialize all "concurrent" breaker calls through one GIL — the opposite of what Go is for. Deployment, static linking, and crash isolation all regress. Non-starter. |
| **gRPC/HTTP sidecar** running the Python kit | Puts a **network hop inside the call you're trying to protect**. A circuit breaker exists to fail *fast and locally*; making `breaker.call()` an RPC adds the latency, queueing, and failure modes the breaker is supposed to absorb. You'd need a breaker around your breaker. Defeats the purpose. |
| **WASM / shared `.so`** | The kit is CPython + C extensions (`cryptography`, `redis-py` hiredis, httpx). Not compilable to a portable Go-loadable artifact. |
| **Rewrite-by-transpile** | Decorators, `ContextVar`, asyncio semantics, and Protocol duck-typing have no mechanical Go equivalent. Any "port" is a re-implementation, not a translation. |

**Rule of thumb:** anything that must run *on the calling path* (retry, breaker,
the `@resilient` decorator, the DNS-pin ContextVar, field crypto) has to be
**native Go**. There is no sane FFI story.

### B.2 What *is* genuinely reusable across languages

The kit was designed so its **distributed state lives in Valkey/Redis behind Lua
scripts** — and Lua + a Redis key schema is language-neutral. These artifacts
port verbatim:

| Reusable artifact | Where | How Go consumes it |
|---|---|---|
| **Throttle token-bucket Lua** | `throttle/lua_scripts.py` | Go loads the *same* `.lua` source, `EVALSHA`s it against the *same* Valkey. Identical refill math → a Python worker and a Go worker share one rate-limit counter. |
| **Breaker state-machine Lua** | `circuit_breaker/lua_scripts.py` | Same — a breaker tripped by Python traffic is OPEN for Go traffic against the same key. |
| **Redis key schemas** | throttle/breaker/cache impls | `throttle:{scope}:{id}:{route}`, breaker state keys, cache keys + TTL conventions. Document them once (Part C.4), both languages honor them. |
| **`ResilienceSettings` shape** | [LLD §10](./LLD.md#10-settings-schema) | Same `RESILIENCE_*` env vars drive both. One ops config, two runtimes. |
| **Exception → HTTP table** | [LLD §11](./LLD.md#11-exception--http-mapping) | Go maps its error types to the *same* status codes + `Retry-After` semantics. Clients see one API contract. |
| **Audit `AuditEvent` schema** | `audit/backends/base.py` | If both write to the same Postgres/ClickHouse audit sink, the row shape must match. Freeze it as a cross-language schema. |
| **Contract test suite** | `tests/contract/` | The behavioral spec. Re-express as Go table tests (Part C.6). |

**So the real interop is at the data/protocol layer, not the code layer.** A Go
service and a Python service can share rate-limit and breaker state through
Valkey precisely because the kit pushed that state into Lua. That is the
"plugin" — not an SDK call, but a shared backend contract.

### B.3 Recommendation

Build a **native `go-resilience-kit`** (Part C) that:

- re-implements the in-process primitives idiomatically in Go, and
- **reuses the Lua scripts and Redis key schemas byte-for-byte** so it shares
  distributed state with the Python kit.

Optionally, a *few* edge concerns can run as a shared service rather than a
library, because they're already network/edge-shaped and not on the hot
internal path: **SSRF validation** and the **audit sink**. Everything else is
in-process Go.

---

## Part C — `go-resilience-kit` blueprint

Goal: feature-parity with the Python kit, idiomatic Go, **shared Valkey state**.
Target a `pkg`-per-subsystem layout mirroring the Python package boundaries.

### C.1 Idiom translation table

| Python kit idiom | Go equivalent |
|---|---|
| `typing.Protocol` (duck-typed) | `interface` (structural — a natural fit; arguably cleaner than Python) |
| `@retry` / `@circuit_breaker` decorators | Higher-order wrappers: `func Retry[T any](cfg, fn func(ctx) (T, error)) (T, error)` and middleware-style `Breaker.Do(ctx, fn)`. Generics give type safety decorators can't. |
| asyncio + `await` | goroutines + `context.Context`. Every primitive takes `ctx` as first arg; cancellation = `ctx.Done()` (maps to "cancellation is not failure"). |
| `ContextVar` (`request_id`, `pinned_dns`) | `context.WithValue` carrying a typed key. The DNS pin rides the request `ctx` instead of a task-local. |
| `MissingExtraError` at import | Build tags / separate modules per backend, or a registry that returns a typed error when a backend isn't compiled in. |
| Entry-point discovery | A `Register(name, factory)` registry + `init()` side-effect imports (the Go convention for `database/sql` drivers). |
| pydantic `ResilienceSettings` | A `Settings` struct + `env`/`koanf`/`viper` loader honoring the **same `RESILIENCE_*` keys**. |
| `MetricsSink` protocol | `Metrics` interface; ship an OTel + Prometheus adapter (Go ecosystem expects it). |

### C.2 Module-by-module port plan

| Kit module | Go package | Ecosystem leverage / notes |
|---|---|---|
| `retry/` | `retry/` | Hand-roll (parity with the kit's decision, [ADR 0002](./adr/0002-handrolled-retry-not-tenacity.md)). Implement the same 3 jitter modes; **decorrelated** is the default. Or wrap `cenkalti/backoff` and pin jitter to match. Contract test asserts timing tolerance band. |
| `circuit_breaker/` | `breaker/` | `memory`: port the state machine (don't reach for `sony/gobreaker` — its semantics differ; parity matters more than reuse). `redis`: **reuse the exact Lua** via `go-redis` `EvalSha`. Same `BreakerState` enum values (`closed/open/half_open` strings) so Redis state is cross-readable. |
| `throttle/` | `throttle/` | `memory`: token bucket in-proc. `redis`: **reuse the exact token-bucket Lua**. Same key schema → shared limits with Python. Return a `Decision{Allowed, Remaining, ResetAfter, Limit}`. |
| `cache/` | `cache/` | `AsyncCache` → `Cache` interface (`Get/Set/Add(NX)/Incr/Delete`). `go-redis` backend; in-memory TTL map default. |
| `decorators.py` | `resilient/` | `Resilient(service, fn)` = breaker-wrapping-retry. **Lock the outer-breaker/inner-retry order** ([ADR 0006](./adr/0006-outer-breaker-inner-retry.md)); filter `ErrServiceUnavailable` out of the retryable set. |
| `registry.py` | `registry/` | Per-service config overlay + `HealthSnapshot()`. Thread-safe `sync.RWMutex` map (Go has no singleton-loop concern). |
| `recovery.py` | `recovery/` | A single background goroutine (not a daemon thread + private loop — Go doesn't need that dance). Re-probe degraded backends, capped backoff, reset provider. |
| `ssrf/` | `ssrf/` | Re-implement CIDR denylist (RFC1918/loopback/link-local/reserved) with `net/netip`. `ResolveAndValidate(url) ([]netip.Addr, error)`. |
| `http_client/` | `httpx/` (or `client/`) | The DNS pin is **cleaner in Go**: set a custom `net.Dialer.Control` / `DialContext` on `http.Transport` that only dials the validated IPs from `ctx`. Composes ssrf → breaker → retry → audit. No httpx-version fragility ([the known httpx gotcha](../CLAUDE.md) disappears). |
| `crypto/fernet.py` | `crypto/` | Fernet is just AES-128-CBC + HMAC-SHA256 + versioned token. Port the token format so **Go can decrypt Python-encrypted fields and vice-versa** (critical if both apps read the same DB column). Keep the env-guard ([ADR 0008](./adr/0008-fernet-env-guard.md)). |
| `audit/` | `audit/` | Buffered channel (Go's native fire-and-forget) → batched writer goroutine. Drop-newest + metric on overflow. **Freeze `AuditEvent` JSON/row schema** to match Python so shared sinks line up. |
| `middleware/` | `middleware/` | Standard `func(http.Handler) http.Handler`. request_id, body_limit, security_headers, CORS, rate_limit_headers, exception_logging. |
| `metrics.py` | `metrics/` | `Metrics` interface + OTel/Prometheus adapters. |
| `health.py` | `health/` | `/readyz` aggregator. |
| adapters (`fastapi`/`django`) | `adapters/{nethttp,gin,echo,chi,fiber}/` | Thin glue per Go web framework — the *Go* analog of the FastAPI/Django adapters. Zero business logic ([ADR 0010](./adr/0010-fastapi-adapter-shape.md) principle holds). |

### C.3 What Go makes *easier* than Python

- **No sync/async split.** The Python kit spends real complexity on
  async-first-with-sync-wrappers, private event loops, and the Django
  daemon-thread bridge ([sync-vs-async.md](./sync-vs-async.md),
  [ADR 0011](./adr/0011-django-sync-async-bridge.md)). In Go, everything is just
  `ctx`-aware functions on goroutines. **A whole class of the kit's hardest
  design problems evaporates** — drop the dual API entirely.
- **DNS pinning** is a first-class `Dialer.Control` hook, not a fragile
  monkeypatched httpx resolver.
- **Cancellation** is `context.Context` end to end.
- **Concurrency primitives** (`sync.Once`, `RWMutex`, channels) replace the
  double-checked-locking + asyncio.Lock + WeakSet machinery.

### C.4 The cross-language contract (freeze these first)

Before writing Go, extract these from the Python kit and pin them as a shared
spec (a `CONTRACT.md` both repos reference):

1. **Lua scripts** — copy `throttle/lua_scripts.py` and
   `circuit_breaker/lua_scripts.py` source into a shared `lua/` dir both
   languages load. Same `SCRIPT LOAD` → same SHA → same behavior. Honor the
   `NoScriptError`→reload-once and `TTL = 2 * per_seconds` rules
   ([LLD §6](./LLD.md#6-throttle--atomic-lua-redis-backend)).
2. **Redis key schemas** — exact key formats and TTL conventions for throttle,
   breaker, cache.
3. **`BreakerState` values** — the literal strings `closed`/`open`/`half_open`
   stored in Redis.
4. **`ResilienceSettings` env keys** — `RESILIENCE_BACKEND`,
   `RESILIENCE_REDIS_URL`, `RESILIENCE_DEFAULTS__*`, etc.
5. **Exception → HTTP table** — Go error types map to the same codes +
   `Retry-After`.
6. **Fernet token format** — if fields are shared in a DB.
7. **`AuditEvent` schema** — if audit sinks are shared.

Items 1–3 are what make a Python worker and a Go worker share live resilience
state. Items 4–7 keep the operational surface identical.

### C.5 Suggested Go module layout

```
go-resilience-kit/
  retry/        breaker/      throttle/     cache/
  resilient/    registry/     recovery/
  ssrf/         client/       crypto/       audit/
  middleware/   metrics/      health/       contextkeys/
  settings/                                  # RESILIENCE_* loader
  lua/                                        # shared scripts (vendored from py kit)
  adapters/
    nethttp/    chi/    gin/    echo/
  internal/testutil/
  contract/                                   # table tests = port of tests/contract/
```

### C.6 Porting the contract suite (parity gate)

The Python `tests/contract/` file-per-primitive, parametrized-over-backends
design ([LLD §12](./LLD.md#12-test-strategy)) becomes Go **table-driven tests**
run against each backend:

```go
for _, backend := range []string{"memory", "redis"} {
    t.Run(backend, func(t *testing.T) {
        b := newBreaker(t, backend) // memory or redis (testcontainers)
        // CLOSED → OPEN after fail_max
        // excluded errors don't count
        // ctx cancellation is NOT a failure
        // concurrent callers see consistent state
        // health_check flips on backend failure
    })
}
```

Run the Go redis-backend tests against the **same Valkey image** the Python kit
uses (`valkey:8`) — and, as a true interop gate, add a mixed test: trip a
breaker / consume a rate-limit slot from the Python kit, then assert the Go kit
observes the shared state. That cross-language test is the real proof the
"plugin via shared backend" model works.

### C.7 Phasing (mirror the kit's milestones)

1. **Core in-proc** — retry, memory breaker, memory throttle, memory cache,
   `Resilient`. (Python M1.)
2. **Redis backends reusing the Lua** — the interop unlock. (Python M2.)
3. **HTTP client + SSRF + crypto** — DNS-pin dialer, CIDR guard, Fernet-compat
   crypto. (Python M3.)
4. **Audit + middleware + metrics.** (Python M4.)
5. **Web-framework adapters** (net/http + one of chi/gin/echo). (Python M5/M6.)
6. **Cross-language contract tests** green against shared Valkey. (New — the
   parity gate.)

---

## TL;DR

- **Reuse the Python kit in Go via SDK/FFI/sidecar?** No for the in-process
  primitives — embedding CPython or RPC-ing a breaker both defeat the kit's
  microsecond, local-failure purpose.
- **What ports cleanly:** the **Valkey state contract** — the Lua scripts, key
  schemas, settings env vars, exception→HTTP table, Fernet token format, and
  audit schema. That's the genuine cross-language "plugin."
- **Do this:** build a native **`go-resilience-kit`** that re-implements the
  primitives idiomatically (Go makes the sync/async and DNS-pin problems
  *easier*) while loading the **same Lua against the same Valkey**, so a Go
  worker and a Python worker share one rate-limiter and one breaker. Freeze the
  Part C.4 contract first; gate parity with the ported contract suite (C.6).
