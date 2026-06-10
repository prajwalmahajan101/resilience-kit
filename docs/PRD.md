# PRD — `resilience-kit`

> Framework-agnostic, **modular**, **pluggable** Python resilience + core-infrastructure kernel. Extracted from `prajwalmahajan101/django_boilerplate` and `prajwalmahajan101/fastapi_boilerplate` to end the dual-write of the same primitives across two starter repos. Every module ships independently installable; every backend is a swappable provider discovered via entry points.

| | |
|---|---|
| **Owner** | Prajwal Mahajan |
| **Status** | Draft v0.1 — pre-implementation |
| **Target release** | PyPI `resilience-kit` v0.1.0 |
| **Effort** | 2–3 weekends |
| **License** | MIT (proposed) |

---

## 1. Problem

Two public boilerplates ship the **same** core infrastructure against two web frameworks. The duplication is broader than just the `resilience/` subtree — it spans the full `core/` package:

| Concern | `django_boilerplate` | `fastapi_boilerplate` | Extraction verdict |
|---|---|---|---|
| Circuit breaker (pybreaker + Valkey Lua) | `apps/core/resilience/circuit_breaker/` | `src/core/resilience/circuit_breaker/` | **IN** |
| Retry decorator | `apps/core/resilience/retry.py` (Tenacity) | `src/core/resilience/retry.py` (handrolled) | **IN** |
| Throttle (token bucket + global Lua) | `apps/core/resilience/throttles/` | `src/core/resilience/throttle/` | **IN** |
| Cache (TTL, backs throttle + blacklist) | `apps/core/resilience/cache/` | `src/core/resilience/cache/` | **IN** |
| Recovery monitor | `apps/core/resilience/recovery.py` | `src/core/resilience/recovery.py` | **IN** |
| Per-service registry + defaults overlay | `apps/core/resilience/registry.py` | `src/core/resilience/registry.py` | **IN** |
| `@log_inbound` / `@log_outbound` audit (api_log) | `apps/core/api_log/` | `src/core/api_log/` | **IN** (this *is* the audit module the spec named) |
| Audit sink backends (noop, ORM/Postgres) | `apps/core/api_log/backends/{noop,orm}.py` | `src/core/api_log/backends/{noop,postgres}.py` | **IN** (as pluggable providers) |
| Payload sanitizers (sensitive-field redaction) | `apps/core/api_log/sanitizers.py` | `src/core/api_log/sanitizers.py` | **IN** |
| DNS-pinned HTTP client (httpx + allow-list + breaker + retry) | `apps/core/utils/http_client/` | `src/core/utils/http_client/` | **IN** |
| SSRF guard (resolve + private-CIDR deny) | — *(missing)* | `src/core/utils/ssrf.py` | **IN** (fills the Django gap) |
| Fernet field crypto | `apps/core/utils/crypto.py` | `src/core/utils/crypto.py` | **IN** |
| Exceptions hierarchy (Transient/External/Infra/Validation/RateLimit/Repository) | `apps/core/exceptions/` | `src/core/exceptions/` | **IN** (kit owns the base classes; exception-handler glue stays per-adapter) |
| Runtime indirection (`get_settings()`) | `apps/core/runtime.py` | `src/core/runtime.py` | **IN** |
| Healthcheck aggregator (`/readyz`) | `apps/core/lifecycle/healthcheck.py` | `src/core/lifecycle/healthcheck.py` | **IN** |
| Metrics shim (RED) | `apps/core/metrics.py` | `src/core/metrics.py` | **IN** (pluggable sink, no Prom dep) |
| Request-ID, body-limit, security-headers, exception-logging, selective-CORS middleware | `apps/core/middleware/` | `src/core/middleware/` | **IN** (provided as framework-agnostic ASGI/WSGI factories + per-adapter wiring) |
| Fire-and-forget task dispatch | `apps/core/dispatch/fire_and_forget.py` | `src/core/utils/fire_and_forget.py` | **IN** |
| Log sanitization, function logger, network/timing/data utils | `apps/core/utils/{log_sanitization,function_logger,network,timing,data}.py` | same | **IN** |
| Background task queue scaffold | `apps/core/tasks/` | `src/core/tasks/` | **IN** (lightweight; no Celery dep) |
| Testing helpers (`reset_all_singletons`, fake clock) | `apps/core/testing/` | `src/core/testing/` | **IN** |
| Response envelope schemas | `apps/core/api_schemas/`, `responses/` | `src/core/responses/` | **OUT** (lives in boilerplate — strongly framework-coupled, low value to share) |
| RBAC registry, auth backends, permissions | `apps/core/auth/`, `apps/core/rbac_registry.py`, `permissions.py` | `src/core/rbac/` | **OUT** (app-domain, not infra) |
| ORM bases — `BaseModel`, `BaseRepository`, `BaseService`, `BaseManager`, `EncryptedString` field | `apps/core/base/` | `src/core/base/` | **OUT** (Django ORM vs SQLAlchemy is too different — these stay in each boilerplate, but they *consume* `resilience_kit.crypto.FernetCipher`) |
| Django `apps.py`, `urls.py`, `views.py`, admin, migrations, settings.py | Django-only | n/a | **OUT** |
| AWS / S3 / SES / Postgres-specific utils | both | both | **OUT** (boilerplate-level integration) |
| OpenAPI metadata, DRF / FastAPI schema customisation | both | both | **OUT** |

The two implementations have **already drifted**: FastAPI is async-native with DNS-pinned SSRF and a `pybreaker|redis|memory|auto` backend selector; Django uses Tenacity for retry, ships DRF throttle classes, but is missing SSRF entirely. Continuing this way means every future fix is a double-PR and the surface keeps diverging.

The extraction is **wider than the original one-pager scoped** — but the IN list above is exactly the surface that is genuinely framework-agnostic and already implemented twice. Everything that's framework- or app-domain-specific (auth, ORM bases, admin, response envelopes) stays in the boilerplates and *depends on* the kit.

---

## 2. Goals

1. **One kernel, two adapters.** Single `resilience_kit` package owns the primitives; thin `resilience_kit.adapters.{django,fastapi}` wire them into each framework's lifecycle.
2. **Same public API in both apps.** A user who learns `@resilient("partner_api")` in FastAPI sees the identical decorator in Django.
3. **Async-first core with sync escape hatches.** Each primitive ships the async API as primary; sync wrappers exist where the primitive is idiomatically sync (Django middleware, Celery tasks).
4. **Migrate both boilerplates to depend on the package.** Embedded `core/resilience/` directories are deleted in the same release cycle; the kit becomes the source of truth.
5. **Ship to PyPI.** `pip install resilience-kit`, type stubs in-tree, `mypy --strict` clean.

## 3. Non-goals

- A metrics layer. Callers wire to Prometheus/OTel themselves via the audit-sink callable.
- A breaker-state web UI.
- Forced sync+async parity for every primitive — pick the natural fit per primitive and document.
- A Flask adapter in v0.1. Listed as stretch in the original spec; defer until someone asks.
- Replacing `pybreaker`, `tenacity`, `valkey-py`, `redis-py`, `httpx`. We use them; we don't re-implement.

---

## 4. Users & use cases

- **Me, on `repay_sync` / `beacon` / future backend repos.** `pip install resilience-kit[fastapi]`, set five env vars, get production-grade resilience without copying boilerplate.
- **Anyone reading the boilerplates as portfolio.** They land on a real PyPI package with its own README, tests, and CI badge — not yet-another `core/resilience/` folder.
- **Future me writing a Hashnode post.** *"Circuit-breaker placement is different in async than sync — here's why."* The DNS-pinned httpx transport is the second post.

### Primary use cases

| # | Story |
|---|---|
| U1 | As a service author, I wrap one outbound HTTP call with `@resilient("partner_api")` and get retry → breaker composition with sane defaults. |
| U2 | As an operator, I set `RESILIENCE_BACKEND=redis` and the kit transparently swaps the in-process backend for a Valkey-backed one shared across workers. |
| U3 | As a security reviewer, I see every outbound HTTP call go through a DNS-pinned session that blocks RFC1918, loopback, link-local, and reserved addresses — and that the pin survives the validate→connect TOCTOU. |
| U4 | As a Django ops person, I drop `resilience_kit.adapters.django` into `INSTALLED_APPS` and `MIDDLEWARE`, get DRF throttle classes + a `/healthz` view + management command for breaker reset. |
| U5 | As a FastAPI dev, I add `resilience_kit.adapters.fastapi.lifespan` to my app and get the recovery monitor + `/readyz` route mounted. |
| U6 | As a maintainer of the two boilerplates, I delete ~3k lines of duplicated code and depend on one package. |

---

## 5. Scope — v0.1

### 5.1 Package layout — modular, single-distribution + extras

Distributed as **one PyPI package** (`resilience-kit`) with extras, not a forest of micro-packages. One package is simpler to release, version, and depend on; modularity is enforced by **import discipline** (each module's hard deps are pure-Python; backends and adapters require extras) and by **entry-point provider discovery** (see §5.3).

If the surface grows past ~10k LOC or a single backend gains an unrelated heavy dep, we can split into namespace packages later without breaking the public API.

```
resilience_kit/
  __init__.py                   # thin: re-exports the most-used decorators only
  runtime.py                    # get_settings() / require() — no global settings import
  context.py                    # request-id / correlation-id ContextVars
  exceptions/                   # TransientError, ExternalTimeoutError, ExternalServiceError,
    __init__.py                 #   ServiceUnavailableError, DecryptionError, ValidationError,
    base.py                     #   RateLimitError, RepositoryError — adapters map to HTTP codes
    infrastructure.py
    validation.py
  registry.py                   # per-service config + defaults overlay + health snapshot
  recovery.py                   # background monitor — re-probes degraded backends, resets providers

  # ---------- independently usable primitives ----------
  retry/                        # core: pure-python, no backends
    decorator.py                # @retry(...) + @retry_on_failure(service_name) — sync + async
  circuit_breaker/
    base.py                     # AsyncBreaker protocol + state enum
    memory_impl.py              # default backend, no extras needed
    pybreaker_impl.py           # extra: [pybreaker]
    redis_impl.py               # extra: [redis] — atomic Lua state transitions
    provider.py                 # entry-point based backend resolver
  throttle/
    base.py                     # token-bucket + sliding-window protocols
    scopes.py                   # ip / endpoint / user_tier / global / burst / auth
    memory_impl.py              # default
    redis_impl.py               # extra: [redis] — global Lua, SHA cache, NoScriptError reload
    provider.py
  cache/
    base.py                     # AsyncCache protocol — get/set/add/incr/delete
    memory_impl.py              # default — TTL aware
    redis_impl.py               # extra: [redis]
    provider.py

  # ---------- I/O & security ----------
  http_client/                  # extra: [http] — the DNS-pinned httpx client
    client.py                   # AsyncAPIClient — composes ssrf + breaker + retry + audit
    session.py                  # pinned_httpx_client() / pinned_requests_session()
    dns_pin.py                  # ContextVar pin + custom resolver hooks
    auth.py                     # bearer / basic / hmac signing helpers
    errors.py                   # request/response error normalization
  ssrf/
    guard.py                    # resolve_and_validate() + assert_allowed_url()
  crypto/                       # extra: [crypto] — `cryptography` dep
    fernet.py                   # FernetCipher + env-guard key derivation

  # ---------- audit / api_log — the @log_inbound/@log_outbound subsystem ----------
  audit/
    __init__.py
    decorators.py               # @log_inbound, @log_outbound — pluggable sink
    dispatch.py                 # fire-and-forget queue → backend
    sanitizers.py               # configurable field redaction
    factory.py                  # build sink from settings
    backends/
      base.py                   # AuditBackend protocol
      noop.py                   # default
      stdlib_logging.py         # default
      postgres.py               # extra: [audit-postgres] (asyncpg)
      django_orm.py             # extra: [django] — uses kit's adapter

  # ---------- observability / lifecycle ----------
  metrics.py                    # RED metrics shim — pluggable sink, no Prom dep
  health.py                     # /readyz aggregator helpers
  middleware/                   # framework-agnostic ASGI/WSGI factories
    request_id.py
    body_limit.py
    security_headers.py
    selective_cors.py
    rate_limit_headers.py
    exception_logging.py
  tasks/                        # lightweight fire-and-forget queue scaffold
    queue.py
    registry.py
  dispatch/
    fire_and_forget.py
  utils/                        # small framework-agnostic helpers
    log_sanitization.py
    function_logger.py
    network.py
    timing.py
    data.py

  testing/
    reset.py                    # reset_all_singletons()
    fakes.py                    # FakeClock, FakeRedis, FakeAuditSink

  py.typed
```

### 5.2 Adapters

```
resilience_kit/adapters/
  django/                       # extra: [django]
    apps.py                     # AppConfig — wires settings, mounts recovery monitor on ready()
    middleware.py               # WSGI/ASGI shims around kit middleware factories
    drf_throttles.py            # DRF throttle classes that delegate to kit throttle
    exception_handler.py        # maps kit exceptions → DRF responses
    fields.py                   # EncryptedCharField — thin wrapper over crypto.FernetCipher
    management/commands/        # `resilience_reset`, `resilience_status`
  fastapi/                      # extra: [fastapi]
    lifespan.py                 # @asynccontextmanager — starts recovery monitor, mounts /readyz
    middleware.py               # Starlette wrappers around kit middleware factories
    dependencies.py             # `rate_limit(scope, rate)` FastAPI dependency
    exception_handlers.py       # maps kit exceptions → JSONResponse
    fields.py                   # EncryptedString SQLAlchemy TypeDecorator
```

Each adapter is ≲ 500 LOC of pure glue. Zero business logic. **Adapters never define new primitives** — they only wire kit primitives into a framework's lifecycle/DI/middleware system.

### 5.3 Pluggability model

Three mechanisms, used in this order of preference:

**(a) Per-module pip extras.** Install only what you need. The core package is pure-Python with no I/O deps.

| Extra | Pulls in | Enables |
|---|---|---|
| *(none)* | — | retry, in-memory breaker, in-memory throttle, in-memory cache, ssrf guard, audit decorators (noop sink), middleware factories, metrics shim, tasks queue, testing helpers |
| `[redis]` | `redis>=5`, `valkey-py` (optional) | redis/valkey backends for breaker, throttle, cache |
| `[pybreaker]` | `pybreaker` | pybreaker backend for circuit breaker |
| `[http]` | `httpx>=0.27,<0.29` | DNS-pinned `AsyncAPIClient` |
| `[requests]` | `requests` | `pinned_requests_session()` |
| `[crypto]` | `cryptography` | `FernetCipher` |
| `[audit-postgres]` | `asyncpg` | postgres audit-log backend |
| `[django]` | `django>=4.2`, `djangorestframework` | Django adapter |
| `[fastapi]` | `fastapi`, `starlette` | FastAPI adapter |
| `[all]` | everything above | — |
| `[dev]` | testcontainers, pytest-asyncio, mypy, ruff, … | development |

Importing a backend whose extra is not installed raises a clear `MissingExtraError("install resilience-kit[redis]")` at import time — never a confusing `ModuleNotFoundError` deep in a stack trace.

**(b) Protocol-based providers.** Every swappable subsystem is a `typing.Protocol` plus a `provider.py` that returns the configured implementation. Callers depend on the protocol, never on a concrete class.

```python
# resilience_kit/cache/base.py
class AsyncCache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    async def incr(self, key: str, amount: int = 1) -> int: ...
    async def delete(self, key: str) -> None: ...
    async def health_check(self) -> HealthSnapshot: ...

# resilience_kit/cache/provider.py
def get_cache(alias: str = "default") -> AsyncCache: ...
async def reset_cache() -> None: ...   # test hook
```

A user-provided backend is registered by either:
- Setting `RESILIENCE_CACHE_BACKEND="myapp.caches:MyMemcachedCache"` (importable string), or
- Exposing a `resilience_kit.cache_backends` entry point in their own package (see (c)).

The set of swappable points at v0.1:

| Subsystem | Protocol | Builtin impls | User-replaceable? |
|---|---|---|---|
| Cache backend | `AsyncCache` | `memory`, `redis` | ✅ |
| Circuit-breaker backend | `AsyncBreaker` | `memory`, `redis`, `pybreaker` | ✅ |
| Throttle backend | `AsyncThrottle` | `memory`, `redis` | ✅ |
| Audit sink backend | `AuditBackend` | `noop`, `stdlib_logging`, `postgres`, `django_orm` | ✅ |
| Audit payload sanitizer | `Sanitizer` | default field-name redactor | ✅ |
| Metrics sink | `MetricsSink` | `noop`, `stdlib_logging` | ✅ (users wire Prometheus / OTel) |
| Settings source | `SettingsSource` | pydantic-from-env | ✅ (Django adapter ships `DjangoSettingsSource`) |
| Clock | `Clock` | `system`, `FakeClock` | ✅ (tests) |
| Audit dispatcher | `Dispatcher` | `fire_and_forget`, `inline` | ✅ |

**(c) Entry-point discovery.** Each swappable subsystem declares a `pyproject.toml` entry-point group. Third-party packages can ship a backend without the kit knowing about them:

```toml
# in someone else's package's pyproject.toml
[project.entry-points."resilience_kit.cache_backends"]
memcached = "rk_memcached:MemcachedCache"

[project.entry-points."resilience_kit.audit_backends"]
clickhouse = "rk_clickhouse_audit:ClickhouseAuditBackend"
```

Entry-point groups exposed by the kit:
- `resilience_kit.cache_backends`
- `resilience_kit.breaker_backends`
- `resilience_kit.throttle_backends`
- `resilience_kit.audit_backends`
- `resilience_kit.audit_sanitizers`
- `resilience_kit.metrics_sinks`
- `resilience_kit.settings_sources`

The provider resolution order is: explicit-callable → settings importable-string → entry-point name → builtin name → fail with a list of available options.

**Net effect:** A user can replace Valkey-backed throttling with Memcached by `pip install rk-memcached` and setting `RESILIENCE_THROTTLE_BACKEND=memcached`. No fork of the kit; no monkey-patching; same `@resilient` decorator everywhere.

### 5.4 Public API (locked at v0.1)

```python
# from resilience_kit import ...
@retry(max_attempts=3, base_delay=1.0, exponential_base=2.0,
       max_delay=60.0, exceptions=(TransientError,))
@retry_on_failure(service_name)            # config pulled from registry
@circuit_breaker(service_name)             # backend selected by provider
@resilient(service_name)                   # circuit_breaker(retry(...))
@log_inbound(sink=..., redact=...)
@log_outbound(sink=..., redact=...)

registry.register_service(name, overrides)
registry.get_config(name)
registry.get_breaker(name)        # async
registry.health_snapshot()        # for /readyz

ssrf.resolve_and_validate(url, *, strict=True) -> set[str]
ssrf.assert_allowed_url(url)
ssrf.pinned_httpx_client(**kwargs)
ssrf.pinned_requests_session()

crypto.FernetCipher.encrypt(plaintext)
crypto.FernetCipher.decrypt(ciphertext)
```

### 5.5 Configuration surface

Single `ResilienceSettings` pydantic v2 model. Resolved via `get_settings()` indirection so callers never import a global. Supports env-var loading with `RESILIENCE_` prefix.

| Key | Default | Notes |
|---|---|---|
| `backend` | `auto` | `auto`/`redis`/`memory`/`pybreaker` |
| `redis_url` | `None` | When set, redis backends become available |
| `defaults.retry.max_attempts` | `3` | |
| `defaults.retry.wait_min` / `wait_max` | `1` / `10` | seconds |
| `defaults.circuit_breaker.fail_max` | `5` | |
| `defaults.circuit_breaker.reset_timeout` | `30` | seconds |
| `defaults.circuit_breaker.success_threshold` | `2` | |
| `defaults.throttle.auth_rate` | `5/min` | |
| `ssrf.block_private_ips` | `True` | |
| `ssrf.outbound_allowlist` | `["*"]` | exact host or `.suffix` |
| `crypto.field_encryption_key` | `None` | required outside dev/test |
| `audit.sink` | stdlib logging | importable string or callable |
| `audit.redact_fields` | `["password", "token", "secret", "authorization"]` | |

---

## 6. Out of scope (v0.1)

Explicitly **not** extracted from the boilerplates (stays in each app):

- **ORM bases** — `BaseModel`, `BaseRepository`, `BaseService`, `BaseManager`, Django admin shims. Too divergent across Django ORM vs SQLAlchemy; *they consume `resilience_kit.crypto.FernetCipher` rather than the other way around.*
- **Response envelopes** — Django uses `apps/core/api_schemas/`, FastAPI uses `src/core/responses/envelope.py`. Strongly framework-coupled; low value to share.
- **Auth / RBAC / permissions** — app-domain logic, not infra.
- **OpenAPI metadata, DRF schema customisation, FastAPI router scaffolding** — framework-specific.
- **AWS / S3 / SES / Postgres-specific utils** — boilerplate-level integration.
- **`apps.py` / `urls.py` / `views.py` / `settings.py` / Django migrations** — Django plumbing.

Also out of scope for v0.1:

- Flask, Celery, Litestar adapters → v0.2+ if requested.
- `resilience_kit doctor` CLI → stretch (M8).
- Sphinx / mkdocs site → README-only at v0.1.
- Prometheus / OTel exporters → callers wire their own `MetricsSink` provider.
- Breaker-state inspection UI → out forever.
- Migrations for legacy embedded breaker state → in-process state is ephemeral; Lua scripts re-load on demand.

---

## 7. Definition of Done

A v0.1 release ships when **all** of the following are true:

- [ ] Package published to PyPI as `resilience-kit==0.1.0` with the full extras matrix from §5.3 (`[redis]`, `[pybreaker]`, `[http]`, `[requests]`, `[crypto]`, `[audit-postgres]`, `[django]`, `[fastapi]`, `[all]`, `[dev]`).
- [ ] Importing a backend whose extra is missing raises `MissingExtraError` with the exact `pip install` hint — covered by a test.
- [ ] All 7 swappable subsystems (cache, breaker, throttle, audit, sanitizer, metrics, settings-source) resolve providers via the protocol → explicit → settings-string → entry-point → builtin chain — covered by tests with a fake third-party entry point.
- [ ] `mypy --strict` clean. `ruff check` + `ruff format` clean. `pydocstyle` + `darglint` pass on all public modules.
- [ ] **Single contract test suite** under `tests/contract/` runs against the in-memory, redis, and (where applicable) pybreaker backends and passes for all three. Same file, three parametrize ids.
- [ ] **Adapter integration tests**: one Django app + one FastAPI app under `tests/integration/` each install the kit, exercise `@resilient`, `@log_outbound`, and the rate-limit throttle, and assert behaviour end-to-end against `testcontainers-redis`.
- [ ] `django_boilerplate` PR opened: `apps/core/resilience/` + `apps/core/utils/crypto.py` removed; depends on `resilience-kit[django,redis]`; all existing tests still pass.
- [ ] `fastapi_boilerplate` PR opened: `src/core/resilience/` + `src/core/utils/{ssrf,crypto}.py` removed; depends on `resilience-kit[fastapi,redis]`; all existing tests still pass.
- [ ] README covers: install, five-minute quickstart per framework, full config reference, the four exceptions callers might catch, and a worked example of `@resilient` + `@log_outbound` around an httpx call.
- [ ] One Hashnode post drafted: *"Circuit-breaker placement is different in async than sync — here's why."* Linked from README.
- [ ] GitHub Actions: lint + types + tests on Python 3.11, 3.12, 3.13 against in-memory backend; redis job on 3.12 only.

---

## 8. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Repo scaffold | `uv` project, layout from §5.1, CI green on an empty test suite, py.typed marker shipped |
| M1 | Core primitives (no backends) | `retry`, in-memory breaker, in-memory throttle, in-memory cache; contract tests pass against memory backends |
| M2 | Redis/Valkey backends | atomic Lua for breaker + throttle; contract suite parametrized; `testcontainers-redis` job green |
| M3 | HTTP client + SSRF + crypto | `AsyncAPIClient` with DNS pin composes ssrf + breaker + retry + audit; Fernet cipher with env-guard |
| M4 | Audit / api_log + middleware + metrics shim | `@log_inbound`/`@log_outbound` with noop + stdlib + postgres backends; framework-agnostic middleware factories; pluggable `MetricsSink`; entry-point discovery wired and tested |
| M5 | FastAPI adapter | lifespan, dependencies, exception handlers, EncryptedString TypeDecorator; `tests/integration/fastapi_app` green |
| M6 | Django adapter | AppConfig, DRF throttles, exception handler, EncryptedCharField, mgmt commands; `tests/integration/django_app` green |
| M7 | Boilerplate migrations | Both boilerplates depend on the kit; all IN-scope modules from §1 deleted from both repos; their CI green |
| M8 | v0.1.0 release | Package on PyPI; README + Hashnode post live; GitHub release tagged |

---

## 9. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **DNS-pinned httpx transport is fiddly across httpx minor versions** | Medium | Medium | Pin `httpx>=0.27,<0.29`; ship `requests`-based fallback; cover with a `dnspython`-mocked test. The pin lives in one module — easy to rewrite per httpx version. |
| **Lua-script semantics differ between Redis and Valkey** | Low | High | Run the contract suite against both `redis:7` and `valkey:8` Docker images. Document supported versions explicitly. |
| **Sync-in-async re-entry breaks Django callers** | Medium | High | Adapters never call async kit primitives directly in sync paths. Django uses sync breaker/retry shims that internally drive a private event loop only when a backend requires it. Document the rule in `docs/sync-vs-async.md`. |
| **Boilerplate users on older versions can't upgrade** | Low | Low | Boilerplates already pin everything; coordinate the migration PRs with a single boilerplate version bump. |
| **`tenacity` vs handrolled retry have different jitter behaviour** | Low | Low | Standardize on decorrelated jitter in the kit. Document the difference in the migration PR. Add a contract test that asserts retry timing falls inside a tolerance band. |
| **First PyPI release naming collision** | Low | Low | `resilience-kit` is unique on PyPI as of writing — reserve the name in M0. |

---

## 10. Open questions

1. **Retry impl: handrolled or `tenacity`?** FastAPI ships handrolled; Django ships Tenacity. Pick one for the kit. *Leaning: handrolled* — fewer transitive deps, async-native, and Tenacity's sync-first design fights the async breaker composition.
2. **Should `@log_inbound` ship without an HTTP layer to hook into?** The decorator is framework-agnostic but every real use is from inside Django middleware / FastAPI dep. *Leaning: yes, ship the decorator; the adapters add the wiring.*
3. **Where does request-ID generation live?** It's used by both audit decorators and the recovery monitor. *Leaning: a tiny `resilience_kit.context` module with a ContextVar; both adapters set it from headers.*
4. **`pybreaker` as a hard dep or optional extra?** It is in both boilerplates today. *Leaning: hard dep — it's small, well-maintained, and the `pybreaker` backend is the cheapest "no Redis configured" production path.*
5. **Versioning policy.** SemVer with the explicit public contract = breaker state-store API + audit sink callable + `ResilienceSettings` shape. Anything else can break in minor versions until v1.0. **Confirm.**

---

## 11. References

- `prajwalmahajan101/fastapi_boilerplate` — current async impl. Notable files: `src/core/resilience/{decorators,retry,registry,recovery}.py`, `src/core/utils/ssrf.py`, `docs/resilience.md`.
- `prajwalmahajan101/django_boilerplate` — current sync impl. Notable files: `apps/core/resilience/{decorators,retry,registry,recovery}.py`, `docs/resilience.md` (state-machine diagrams).
- `prajwalmahajan101/project-todo` — `projects/prajwal-resilience-kit.md` (the original one-pager spec this PRD supersedes; the file kept its original name in that repo).
- Hashnode (planned): *Circuit-breaker placement is different in async than sync — here's why.*
