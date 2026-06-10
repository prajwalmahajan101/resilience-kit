# Roadmap — `resilience-kit` v0.1

Feature-level breakdown of the milestones from [PRD.md §8](./PRD.md). Each milestone has a goal, a concrete feature list, and an "exit when" gate. Milestones are sequential except where noted.

Legend: 🟦 core primitive · 🟩 backend / provider · 🟨 adapter · 🟧 dev infra · 🟥 release gate

---

## Tagging convention

Two kinds of tags ship from this repo. They mean different things and the GitHub
UI should treat them differently.

| Tag pattern | Meaning | GitHub Release? | Installable from PyPI? |
|---|---|---|---|
| `milestone/m0` … `milestone/mN` | **Dev checkpoint.** A roadmap milestone passed its exit gate; the next milestone can start against this SHA. Not a user-facing version. | ❌ no | ❌ no |
| `v0.1.0`, `v0.1.1`, … | **Shippable release.** Trusted-publish to PyPI, GitHub Release with auto-generated notes, README install command points at this. | ✅ yes | ✅ yes |

The first `v*` tag lands at the end of M8 (the v0.1 release gate). Until then,
every `milestone/m*` is just a "we passed this checkpoint, don't blame the next
milestone for breaking the previous one" marker — useful for `git bisect`, not
for end users.

If you see a `milestone/m*` tag without a matching GitHub Release, that's by
design — please don't open a PR to "fix" it.

---

## M0 — Repo scaffold 🟧

**Goal.** A green-CI empty package the user can `pip install -e` and import.

**Features.**
- `pyproject.toml` (uv-managed) — name, version `0.1.0.dev0`, license, urls, classifiers, extras matrix from PRD §5.3 declared but with empty deps.
- Source layout: `src/resilience_kit/__init__.py`, `py.typed` marker, empty submodule stubs matching PRD §5.1.
- `ruff.toml` (lint + format), `mypy.ini` (`--strict`), `pydocstyle` config in `pyproject.toml`, `darglint` config.
- `.pre-commit-config.yaml` — ruff, mypy, pydocstyle, darglint, end-of-file-fixer, check-yaml.
- GitHub Actions: `.github/workflows/ci.yml` — matrix on Python 3.11/3.12/3.13, jobs for lint / types / tests; PR template; CODEOWNERS.
- `tests/` skeleton: `conftest.py`, `tests/contract/__init__.py`, `tests/integration/__init__.py`, one trivial passing test per area so CI has something to run.
- README badges activated (CI, PyPI, license).
- `CHANGELOG.md` (Keep-a-Changelog format) with the `Unreleased` section.

**Exit when.** `uv sync --all-extras --dev` succeeds. CI is green on `main`. `import resilience_kit` works.

---

## M1 — Core primitives, in-memory only 🟦🟩

**Goal.** The full public decorator API works end-to-end with zero I/O dependencies.

**Features.**
- `exceptions/` — `TransientError`, `ExternalTimeoutError`, `ExternalServiceError`, `ServiceUnavailableError`, `RateLimitError`, `DecryptionError`, `ValidationError`, `RepositoryError`, `MissingExtraError`. All carry a stable `error_code` and a `details` dict.
- `runtime.py` — `get_settings()` indirection over a pluggable `SettingsSource` protocol. Builtin: pydantic-v2-from-env source. `require(key)` helper.
- `context.py` — `request_id`, `correlation_id` ContextVars + helpers.
- `registry.py` — per-service config registry with defaults overlay, `register_service()`, `get_config()`, `get_breaker()`, `health_snapshot()`. Defaults loaded from `ResilienceSettings.defaults`.
- `retry/` — `@retry(...)` (explicit knobs) + `@retry_on_failure(service_name)` (registry-driven), sync + async, decorrelated jitter, on_error callback, total-deadline budget.
- `circuit_breaker/base.py` — `AsyncBreaker` protocol, `BreakerState` enum, `BreakerConfig` dataclass.
- `circuit_breaker/memory_impl.py` — in-process async breaker with injectable clock.
- `circuit_breaker/provider.py` — provider resolution chain (explicit → settings string → entry point → builtin → fail).
- `throttle/base.py` — `AsyncThrottle` protocol, `Rate.parse("60/min")` parser, scope enums.
- `throttle/memory_impl.py` — token bucket + sliding window, async, with injectable clock.
- `throttle/scopes.py` — `ip` / `endpoint` / `user_tier` / `global` / `burst` / `auth` key derivation.
- `cache/base.py` — `AsyncCache` protocol — `get/set/add/incr/delete/health_check`.
- `cache/memory_impl.py` — TTL-aware in-process cache with monotonic-clock expiry.
- `decorators.py` — `@circuit_breaker(name)`, `@resilient(name)` (breaker ∘ retry), sync + async detection.
- `testing/` — `reset_all_singletons()`, `FakeClock`, in-memory `FakeAuditSink` for tests.
- **Contract test suite** under `tests/contract/` — one `test_breaker_contract.py`, `test_throttle_contract.py`, `test_cache_contract.py`, `test_retry_contract.py`. Parametrized via fixtures over `(backend_name, factory)` — at M1 only `memory` is wired.

**Exit when.** Contract suite passes for the `memory` backend. `@resilient("svc")` correctly composes retry inside a breaker against a stub upstream. `mypy --strict` is clean.

---

## M2 — Redis / Valkey + pybreaker backends 🟩

**Goal.** Same contract suite passes against three more backends; provider chain works.

**Features.**
- `circuit_breaker/pybreaker_impl.py` — wraps `pybreaker` behind `AsyncBreaker`. Extra: `[pybreaker]`.
- `circuit_breaker/redis_impl.py` — atomic Lua state transitions (OPEN/HALF_OPEN/CLOSED), TTL refresh, `SCRIPT LOAD` + `NoScriptError` reload, fail-open on Redis error with degraded health flag. Extra: `[redis]`.
- `throttle/redis_impl.py` — global Lua for token bucket + sliding window, SHA cache, NoScriptError reload, atomic counter increments. Extra: `[redis]`.
- `throttle/lua_scripts.py` — script bodies, version tags, SHA registry.
- `cache/redis_impl.py` — async Redis cache via `redis-py>=5` async client. Extra: `[redis]`.
- `recovery.py` — singleton background monitor. Owns the list of aliases that degraded at boot, polls with exponential backoff, resets cached providers once a backend recovers. Async; designed to be launched from a lifespan/AppConfig.
- Entry-point group registration in `pyproject.toml` for the three swappable subsystems.
- `MissingExtraError` raised at import time with the exact `pip install` hint when a backend module is imported without its extra.
- Contract suite parametrized over `memory`, `redis`, `pybreaker` — same test file, three IDs.
- `testcontainers-redis` integration job in CI (Python 3.12 only).
- CI matrix sub-job: run the redis backends against both `redis:7` and `valkey:8` Docker images.

**Exit when.** `pytest tests/contract -q` green for all 3 backends. Recovery monitor flips a degraded provider back to its primary in under 5s in a kill-and-restart-redis test.

---

## M3 — HTTP client + SSRF + crypto 🟦 ✅ shipped

**Goal.** One outbound HTTP call is fully protected with one decorator.

**Features.**
- `ssrf/guard.py` — `resolve_and_validate(url, strict=True) -> set[str]`, `assert_allowed_url(url)`, `assert_public_url(url)` shim. Rejects non-http(s), private/loopback/link-local/reserved/multicast/unspecified.
- `ssrf/` outbound allow-list — exact-host and `.suffix` matching; settings-driven, `["*"]` permissive default.
- `http_client/dns_pin.py` — `pinned_dns: ContextVar[dict[str, set[str]] | None]`, `@contextmanager pinned()`, custom httpx resolver hook.
- `http_client/session.py` — `pinned_httpx_client(**kwargs)`, `pinned_requests_session()` factories.
- `http_client/auth.py` — `BearerAuth`, `BasicAuth`, `HMACAuth` helpers.
- `http_client/errors.py` — `RequestError`, `ResponseError`, `TimeoutError` normalization (mapped onto kit exceptions).
- `http_client/client.py` — `AsyncAPIClient(service=name)`. Composes: SSRF guard → DNS pin → `@resilient(name)` → audit (`@log_outbound`) → request. Sync mirror via internal loop only if no loop is running.
- `crypto/fernet.py` — `FernetCipher.encrypt/decrypt`. SHA-256-of-secret key derivation. Env-guard: refuses to start in prod without `field_encryption_key`; dev-only fallback to `secret_key` with warning. `lru_cache(maxsize=1)` instance. Extra: `[crypto]`.
- `crypto/exceptions.py` — `FernetUnavailableError`, `EncryptionConfigError`, `DecryptionError`.
- Tests: TOCTOU DNS-rebinding test (zone returns public IP at validate, private at connect — must be blocked); allow-list bypass attempts; Fernet round-trip; key-rotation `DecryptionError` mapping.

**Exit when.** `AsyncAPIClient` survives the DNS-rebinding test; `FernetCipher` round-trips and refuses prod-without-key.

---

## M4 — Audit (api_log) + middleware + metrics + entry-point wiring 🟦🟩 ✅ shipped

**Goal.** Observability primitives ship; third-party backends are discoverable.

**Features.**
- `audit/decorators.py` — `@log_inbound(...)`, `@log_outbound(...)`. Both decorate sync + async. Capture: request_id, service, method, payload (post-sanitization), latency, outcome, error_code.
- `audit/sanitizers.py` — `Sanitizer` protocol + default field-name redactor; configurable redact set; deep-walks dicts/lists.
- `audit/dispatch.py` — fire-and-forget dispatcher (default) + inline dispatcher (for tests). Bounded queue, drop-newest-on-overflow with a counter metric.
- `audit/factory.py` — build sink + sanitizer + dispatcher from settings.
- `audit/backends/base.py` — `AuditBackend` protocol.
- `audit/backends/noop.py`, `audit/backends/stdlib_logging.py` — defaults, no extras.
- `audit/backends/postgres.py` — asyncpg writer with batching; schema-migration SQL shipped as a string for callers to apply. Extra: `[audit-postgres]`.
- `metrics.py` — RED metrics (rate / errors / duration) emission points in retry, breaker, throttle, http_client. Pluggable `MetricsSink` protocol; builtin `noop` and `stdlib_logging` sinks.
- `health.py` — `/readyz` aggregator: collects `health_check()` from every provider, returns degraded/degraded-but-serving/ok.
- `middleware/` — framework-agnostic ASGI/WSGI factories: `request_id`, `body_limit`, `security_headers`, `selective_cors`, `rate_limit_headers`, `exception_logging`.
- `tasks/queue.py` + `tasks/registry.py` — lightweight in-process fire-and-forget task queue (no Celery dep). Bounded, with graceful drain on shutdown.
- `dispatch/fire_and_forget.py` — promoted from utils into a top-level module; used by audit + tasks.
- **Entry-point discovery**: kit reads `importlib.metadata.entry_points(group=...)` for all 7 swappable groups; precedence chain (explicit → settings string → entry point → builtin → fail with available-options list) implemented in one shared `provider_chain()` helper.
- Test: ship a `tests/fixtures/fake_third_party/` mini-package with a fake `resilience_kit.cache_backends` entry point; resolution-chain test installs it via `uv pip install -e` in CI.

**Exit when.** A fake third-party cache backend resolves via entry point. `@log_outbound` writes to the postgres backend in a testcontainers Postgres test. `/readyz` correctly reports degraded when redis is killed.

---

## M5 — FastAPI adapter 🟨

**Goal.** A real FastAPI app uses the kit end-to-end.

**Features.**
- `adapters/fastapi/lifespan.py` — `@asynccontextmanager` lifespan that starts the recovery monitor + audit dispatcher, mounts `/readyz` and `/healthz` routes, drains the audit queue on shutdown.
- `adapters/fastapi/dependencies.py` — `rate_limit(scope, rate)` FastAPI dependency; `request_id_dep` for handlers that need it.
- `adapters/fastapi/middleware.py` — Starlette wrappers around the kit's middleware factories.
- `adapters/fastapi/exception_handlers.py` — `install(app)` registers handlers mapping every kit exception to the right JSON envelope + HTTP status (`ServiceUnavailableError` → 503, `RateLimitError` → 429 with `Retry-After`, `ValidationError` → 400, etc.).
- `adapters/fastapi/fields.py` — `EncryptedString` SQLAlchemy `TypeDecorator` over `FernetCipher`.
- `tests/integration/fastapi_app/` — minimal FastAPI app exercising `@resilient`, `rate_limit`, an `AsyncAPIClient` call, an `EncryptedString` column. `httpx.AsyncClient` end-to-end tests against `testcontainers-redis` + `testcontainers-postgres`.
- Adapter is ≲ 500 LOC of pure glue. Zero business logic.

**Exit when.** `tests/integration/fastapi_app` green. A reviewer can copy the example app's `main.py` into a new repo, `pip install`, and have working resilience.

---

## M6 — Django adapter 🟨

**Goal.** A real Django + DRF app uses the kit end-to-end.

**Features.**
- `adapters/django/apps.py` — `AppConfig` reading `settings.RESILIENCE`, registering services into the registry on `ready()`, launching the recovery monitor in a daemon thread (since Django is sync).
- `adapters/django/middleware.py` — WSGI/ASGI middleware classes wrapping the kit's middleware factories.
- `adapters/django/drf_throttles.py` — `IPThrottle`, `UserTierThrottle`, `EndpointThrottle`, `BurstThrottle`, `AuthThrottle` DRF classes that delegate to the kit throttle.
- `adapters/django/exception_handler.py` — DRF exception handler `handle(exc, context)` mapping kit exceptions to DRF responses.
- `adapters/django/fields.py` — `EncryptedCharField` model field over `FernetCipher`.
- `adapters/django/management/commands/resilience_status.py` — prints per-service breaker state + cache/throttle/audit health.
- `adapters/django/management/commands/resilience_reset.py` — `./manage.py resilience_reset [service_name|--all]` force-closes a breaker.
- `tests/integration/django_app/` — minimal Django + DRF project exercising the throttles, the EncryptedCharField, an `AsyncAPIClient`-via-sync call, mgmt commands. Runs against `testcontainers-redis` + `testcontainers-postgres`.
- Sync-in-async handling documented in `docs/sync-vs-async.md`: adapter calls the breaker/retry sync wrappers; the wrappers drive a private event loop only when a backend requires it.

**Exit when.** `tests/integration/django_app` green on Django 4.2 LTS and 5.x. `./manage.py resilience_status` and `resilience_reset` work against a live Valkey container.

---

## M7 — Boilerplate migrations 🟥

**Goal.** Both boilerplates depend on the kit; embedded code deleted; their local test suites green.

**Sequencing.** FastAPI first, then Django — lessons feed the Django PR and the
migration doc. Boilerplates pin against `git+ssh://…@milestone/m7-rc1` during
M7; re-pinned to `resilience-kit==0.1.0` at M8.

**Features.**
- This repo (`feat/m7-boilerplate-migrations` branch):
  - `docs/MIGRATION-from-boilerplate-embedded.md` — install, deletion + import-rewrite table per module, settings translation (`CIRCUIT_BREAKER_CONFIG` / `RATE_LIMIT_CONFIG` / `FIELD_ENCRYPTION_KEY` / Valkey URLs → `RESILIENCE_*`), FastAPI lifespan diff, Django `INSTALLED_APPS`/`MIDDLEWARE`/`RESILIENCE` diff, DRF throttle swap, `EncryptedCharField`/`EncryptedString` swap, test-suite delta.
  - Tag `milestone/m7-rc1` so boilerplates have a stable pin (dev checkpoint, not a release — see Tagging convention above).
- Branch `feat/depend-on-resilience-kit` in `fastapi_boilerplate`:
  - Delete: `src/core/resilience/`, `src/core/api_log/`, `src/core/utils/{ssrf,crypto,log_sanitization,function_logger,network,timing,data,fire_and_forget}.py`, `src/core/utils/http_client/`, `src/core/middleware/{request_id,body_limit,security_headers,selective_cors,rate_limit_headers,exception_logging}.py`, `src/core/lifecycle/healthcheck.py`, `src/core/metrics.py`, `src/core/testing/reset.py`.
  - **Keep**: `src/core/tasks/` (Celery wrapper — out of scope for M7; the kit's `tasks/` is a lightweight in-process queue for its own audit dispatcher, not a Celery replacement). `src/core/dispatch/` does not exist in this repo.
  - **Keep** `src/core/exceptions/` as the boilerplate's domain layer; replace its infra exception classes with re-exports from `resilience_kit.exceptions` where they overlap.
  - Add `resilience-kit[fastapi,redis,http,crypto,audit-postgres] @ git+ssh://…@milestone/m7-rc1` to `requirements/base.in`; `pip-compile`.
  - Rewrite imports: `from src.core.resilience import resilient` → `from resilience_kit import resilient`, etc.
  - Replace lifespan setup with `resilience_kit.adapters.fastapi.resilience_lifespan` composed around the boilerplate's DB-engine + repository init.
  - Run existing test suite; fix any drift.
- Branch `feat/depend-on-resilience-kit` in `django_boilerplate`:
  - Delete: `apps/core/resilience/`, `apps/core/api_log/`, `apps/core/utils/{crypto,log_sanitization,function_logger,network,timing,data}.py`, `apps/core/utils/http_client/`, `apps/core/middleware/{request_id,body_limit,security_headers,selective_cors,rate_limit_headers,exception_logging}.py`, `apps/core/lifecycle/healthcheck.py`, `apps/core/metrics.py`, `apps/core/tasks/`, `apps/core/dispatch/fire_and_forget.py`, `apps/core/testing/reset.py`, `apps/core/runtime.py`, `apps/core/resilience/throttles/drf_impl.py`.
  - **Keep**: boilerplate-specific middleware (`request_logging`, `throttling`, `metrics_middleware`) — not in the kit's deletion set.
  - **Partial** `apps/core/exceptions/`: gut `{infrastructure,rate_limit,validation,repository}.py` → re-export from `resilience_kit.exceptions`. **Keep** `auth.py`, `api.py`, `handler.py`, `utils.py` as boilerplate domain.
  - `INSTALLED_APPS += ["resilience_kit.adapters.django"]`; MIDDLEWARE swap to `resilience_kit.adapters.django.middleware.*`; add `RESILIENCE = {...}` dict (consumed by `DjangoSettingsSource`); delete legacy `CIRCUIT_BREAKER_CONFIG` / `RATE_LIMIT_CONFIG` / `FIELD_ENCRYPTION_KEY` overlays.
  - Remove `_start_recovery_monitor` from `apps/core/apps.py` — kit's `ResilienceConfig.ready()` owns it.
  - DRF throttle class swap (`UserTierThrottle`, `BurstThrottle`, `EndpointThrottle`, `IPThrottle`, `AuthThrottle` from `resilience_kit.adapters.django.drf_throttles`).
  - `EncryptedCharField` import swap (re-export from `resilience_kit.adapters.django.fields`).
  - DRF `EXCEPTION_HANDLER` → `resilience_kit.adapters.django.exception_handler.handle`.
  - Delete boilerplate's `resilience_status` / `resilience_reset` management commands (kit ships them).
- One PR each, linked from the kit's v0.1.0 release notes.
- Verify: both boilerplates' local `pytest` + `pre-commit` green; sample apps still boot and pass smoke tests; deployment configs unchanged. **Note:** neither boilerplate currently has `.github/workflows/`; standing up CI is a follow-up chore PR, not part of M7.

**Exit when.** Both PRs open with green local test runs; embedded `core/resilience/` and friends are gone from both repos. Tag `milestone/m7` on this repo's `main` after both boilerplate PRs merge.

---

## M8 — v0.1.0 release 🟥

**Goal.** Published, announced, recommended.

**Features.**
- Version bump `0.1.0.dev0` → `0.1.0` in `pyproject.toml`.
- `CHANGELOG.md` Unreleased → `0.1.0` section, with breaking-changes/added/changed/fixed buckets.
- Trusted publishing to PyPI via GitHub Actions OIDC (no token in CI).
- Release workflow: tag `v0.1.0` → builds sdist + wheel → publishes to PyPI → drafts GitHub release with auto-generated notes.
- README badges flip to real PyPI version/downloads.
- Hashnode post live: *Circuit-breaker placement is different in async than sync — here's why.* Linked from README.
- Boilerplate PRs (from M7) merged within 48h of release.
- `docs/SECURITY.md` — vulnerability reporting policy.
- `docs/CONTRIBUTING.md` — dev setup, contract-suite expectations, how to add a backend.

**Exit when.** `pip install resilience-kit==0.1.0` works for someone who has never seen this repo, against the README quickstart, in under 5 minutes.

---

## Beyond v0.1 (parking lot)

Items below come from two streams: the original v0.1 design that explicitly punted things (Flask + Celery adapters, doctor CLI, Sphinx docs), and the M7 boilerplate dogfooding reports that surfaced ergonomic + operational gaps too large to retrofit into 0.1.x. Items tagged **[dogfooding]** trace back to a specific finding in the FastAPI / Django M7 integration reports; treat them as evidence-backed, not aspirational. Version targets are aspirational — items move forward when an adopter asks for them, not on a fixed cadence.

### v0.1.x patch line — additive, non-breaking

Cut as needed during v0.1.0 → v0.2.0. Single-feature minor versions; no API removals.

- **`reset_all_singletons_async()`** — async-def shim alongside the sync `reset_all_singletons()` so test harnesses that previously used `async def` keep their signature without a `to_thread` wrapper. ~10 LOC. **[dogfooding]** FastAPI report §3.3.
- **`from_exception(exc, *, envelope_cls=None)`** — kit-side helper that builds a JSONResponse from a `ResilienceKitError`, optionally re-shaped through a caller-supplied envelope class. Lets adopters keep their existing `{success, message, data, errors, request_id}` wire shape without re-implementing the handler. ~30 LOC. **[dogfooding]** FastAPI report §0.2 + Report-2 §wishlist-4.
- **`AuthType` deprecation shim** — re-export the legacy `AuthType` enum name from `http_client.auth` with a `DeprecationWarning` for one minor cycle so the M7 codemod path is graceful for repos still on the enum dispatch pattern. ~15 LOC. **[dogfooding]** FastAPI report §3.8 + Report-2 §wishlist-7.
- **`legacy_env_alias()` translator** — utility that callers import once in their settings module to map legacy env-var names (`RATE_LIMIT_*`, `CIRCUIT_BREAKER_*`, `FIELD_ENCRYPTION_KEY`, …) onto the `RESILIENCE_*` schema with a one-time `DeprecationWarning` per alias used. Removes the silent operator-tuning loss that hit the Django dogfooding migration. ~40 LOC + an env-alias table. **[dogfooding]** Django report §3.3 + §4.6.
- **`verify_envelope_contract()` test helper** — kit-side pytest fixture that asserts "given your project's `EXCEPTION_HANDLER`, raising each `ResilienceKitError` subclass returns your envelope shape". Lets adopters pin the bridge invariant from §3.6 of the Django report (`BaseCustomError(ResilienceKitError)` is one load-bearing line with no test today). ~50 LOC. **[dogfooding]** Django report §4.5.

### v0.2 — adopter ergonomics

Theme: close the three biggest "needed this in production at any scale" gaps the FastAPI dogfooding flagged. Each is small in code but high in noticeable-friction-eliminated.

- **FastAPI health-check routers in `adapters/fastapi`** — `create_health_router()` / `create_readiness_router()` factories that mount `/healthz` + `/readyz` with per-backend probe rows. Every adopter hand-rolls ~80 LOC of this today. **[dogfooding]** FastAPI report §3.7 + Report-2 §wishlist-1 (highest impact).
- **`MetricsSink` cardinality contract** — promote the boilerplate's `_assert_bounded` pattern (~80 LOC) into either a `BoundedMetricsSink` decorator or a Protocol upgrade with a `cardinality_budget: int` knob. The current "log this dict" `MetricsSink` shape is the single biggest production-risk regression in v0.1 — the first time someone slips a `request_id` label past code review, Prometheus explodes. **[dogfooding]** FastAPI report §3.6 + Report-2 §lost-3 + Report-2 §wishlist-2 + Django report §3.2.
- **Free-function metrics shim** — ship `from resilience_kit.metrics import record_duration, record_counter, record_gauge` over the Protocol sink so projects can keep their existing call sites and still tee into the kit's pluggable backend. Lands alongside the cardinality contract above. ~40 LOC. **[dogfooding]** Django report §4.7.
- **`bind_to(consumer_ctxvar)` helper** on `resilience_kit.context.request_id` — first-class story for adopters who keep their own request-id ContextVar (every existing FastAPI / Django boilerplate does). Eliminates the silent-null-correlation footgun the FastAPI dogfooding hit on commit 1. **[dogfooding]** FastAPI report §0.1 + Report-2 §wishlist-5.
- **Real `DjangoSettingsSource`** — make `settings.RESILIENCE = {...}` actually load-bearing. The Django adapter currently reads only the `services` key out of the dict; the rest is documentation in Python-dict shape. A real source maps the whole tree onto `ResilienceSettings`, so Django adopters configure the kit through Django's own settings instead of env vars. The Django dogfooding report calls this the "single highest-leverage doc + code change the kit can ship next." ~150 LOC + tests. **[dogfooding]** Django report §3.5 + §4.1.
- **`GlobalThrottle`** — Valkey + Lua-backed system-wide cap (e.g. `10_000/min` regardless of scope key). The Django boilerplate had this as a defence layer for deployments without an L7 reverse proxy and lost it in the migration; restore via the kit. ~120 LOC of Lua + Python wrapper. **[dogfooding]** Django report §3.1 + §4.3.
- **Flask adapter** — same shape as fastapi / django: `install_middleware_stack`, `install_exception_handlers`, lifespan-equivalent via Flask app factory hooks.
- **Celery adapter** — `@task_retry_policy(...)` decorator that composes with Celery's own retry, plus `adapters/celery` lifespan that owns the recovery monitor inside a Celery worker process.
- **`tasks.local_queue` rename** (or namespace hint) — disambiguate the kit's in-process `tasks.queue` / `tasks.registry` from Celery-style task names, which Django/FastAPI boilerplates already use under the same identifier. **[dogfooding]** FastAPI report §3.12. **Breaking inside v0.2**; ship an alias module for one release.

### v0.3 — operational depth

Theme: the ops-team knobs and richer shapes that v0.1 deliberately narrowed.

- **Multi-alias Redis support** — `redis_urls: dict[str, str]` (or per-subsystem `RESILIENCE_<sub>__REDIS_URL` env keys) so cache / throttle / breaker / audit can run on separate Redis instances. Real high-throughput shops need this; both M7 boilerplates lost the named-alias dict in the migration. **[dogfooding]** FastAPI report §3.4 + Report-2 §lost-1 + Report-2 §wishlist-3.
- **`HTTPAuditEvent` subclass** — richer audit shape extending `AuditEvent` with separate `request_headers` / `request_body` / `response_status` / `response_body_redacted` / `ttl_expires_at` / `environment` columns. Lets HTTP services upgrade off the generic `payload: Mapping` without forking the dispatcher. The M7 boilerplates explicitly chose to keep their own audit pipeline rather than downgrade to v0.1's shape — this closes the gap. **[dogfooding]** FastAPI report §1.audit + Report-2 §lost-4 + Report-2 §wishlist-6.
- **`AsyncFernetCipher`** — async surface mirroring the sync class so adopters stop wrapping in `asyncio.to_thread`. Same key-derivation + env-guard rules as the sync class. **[dogfooding]** Report-2 §wishlist-8.
- **`backend_name` + `reset_backend(alias)` surgical-reset API** — restore the diagnostic + targeted-reset capability the boilerplate had (`"show me what's actually running"` + manual reset on a single backend without touching the rest). Expose via the registry, mirror through both adapters' management commands. **[dogfooding]** Report-2 §lost-2.
- **Litestar adapter** — same surface as fastapi.
- **`resilience_kit doctor` CLI** — scans a project for unprotected outbound calls (no `@resilient` on a function that does HTTP), unbounded metric labels (catches what v0.2's cardinality contract gates at runtime), and legacy env-var names that survived the M7 migration.

### v0.4 — visibility

- **Sphinx + `mkdocs-material` docs site** under `resilience-kit.dev` (or GitHub Pages until DNS lands). Replaces the `docs/` markdown tree as the canonical reference; the markdown stays for in-repo browsing + greppability.

### Maybe (no version target)

- **`pyo3`-built hot-path primitives** if the pure-Python breaker becomes a bottleneck under load. Unlikely; flagged for measurement post-release.
- **Memcached / ScyllaDB / DynamoDB backends** as separate `rk-*` packages (third-party shape, not in-kit — exercises the ADR 0004 entry-point precedence guarantee in production).
- **First-class envelope-override hook** — superset of v0.1.x `from_exception(...)` that lets adopters register their `{success, message, data, errors, request_id}` envelope class once at startup and have every kit handler use it automatically. Land in v0.2 if the v0.1.x patch-level helper isn't ergonomic enough.

### Maintenance lines

Always-on commitments that don't need a version slot:

- **Dependabot** runs weekly across actions + Python deps; security patches merge on the same day they're filed.
- **CHANGELOG `[Unreleased]`** gets a one-line entry for every user-visible change, no exceptions, so each `vX.Y.Z` cut has notes ready.
- **Boilerplate dogfooding pin** — kit and both boilerplates re-test their integration on every kit minor (`v0.2.0`, `v0.3.0`, …) before the kit's tag is pushed.
