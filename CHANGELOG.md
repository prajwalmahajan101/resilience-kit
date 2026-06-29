# Changelog

All notable changes to `resilience-kit` are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `[prometheus]` extra with a `prometheus_client`-backed `PrometheusMetricsSink` (select `RESILIENCE_METRICS_SINK=prometheus`), mapping the kit's `incr`/`timing`/`gauge` onto namespaced Counters/Histograms/Gauges for a stock `/metrics` endpoint. `metrics.py` is now the `metrics/` package (all v0.1 public names re-export unchanged). (Lane C #C2)
- `BoundedMetricsSink` + `settings.metrics_cardinality_budget`: caps distinct tag-value combinations per metric, dropping labels and emitting `metrics.cardinality_exceeded` past the budget so a stray high-cardinality label (e.g. `request_id`) can't explode the backend. Plus a `record_counter` / `record_duration` / `record_gauge` free-function shim over the active sink. New ADR-0015. (Lane C #C2)
- Field-crypto key rotation via `MultiFernet`. `settings.crypto.field_encryption_keys` is now an ordered list (primary first; trailing keys decrypt-only): encryption uses the primary, decryption tries each key, so ciphertext written under a retired key still decrypts. `FernetCipher.rotate(token)` re-encrypts an existing token under the current primary without exposing plaintext. The singular `field_encryption_key` is kept as a deprecated alias for one minor cycle. New ADR-0014 + `docs/key-rotation.md` runbook. (Lane C #C1)
- Value-scanning audit redactors: `RegexRedactor` (field-name matching plus regex over string leaves) and the batteries-included `IndiaFintechRedactor`, registered under the `india_fintech` sanitiser entry point. Ship `GLOBAL_PII_PATTERNS` (email, IBAN, Luhn-checked credit card) and `INDIA_PII_PATTERNS` (PAN, IFSC, Indian mobile, Aadhaar, bank account) so PII embedded *inside* an innocuous field value (e.g. `{"notes": "PAN ABCDE1234F"}`) is masked, not just whole sensitive keys. Select via `RESILIENCE_AUDIT__SANITIZER=india_fintech`. (Lane C #C5)
- `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1. Linked from README and `CONTRIBUTING.md`. (Lane A #A6)
- `.github/workflows/dependabot-automerge.yml` — auto-merges Dependabot patch/minor PRs once required checks pass; majors stay manual. (Lane A #A5)
- CI gates ported from `colending_partner`: a `pip-audit` (OSV) dependency-vuln job, a `uv lock --check` lockfile-drift job, a dead public-symbol check (`scripts/check_dead_symbols.py` + pre-commit hook), and a sticky PR status comment. (Lane A #A11–#A14)
- `--cov-fail-under` coverage gate on the unit/contract CI job. (Lane A #A7)
- `Makefile` with the local dev/CI-gate targets (`lint`, `types`, `test`, `audit`, `lock-check`, `dead-symbols`, `gate`).
- `AsyncAPIClient.request()` (and the verb shortcuts) accept `idempotency_key=` and `auto_idempotency_key=`. The `Idempotency-Key` header is resolved once before the retry loop, so a POST/PUT/PATCH retried after a timeout sends the byte-identical key on every attempt — the upstream dedupes instead of double-processing (the canonical double-charge bug). Precedence: explicit key > caller header > auto-generated; auto-gen is scoped to POST/PUT/PATCH and off by default. New ADR-0012. (Lane B #B2)
- Throttle `fail_mode` setting (`defaults.throttle.fail_mode`, default `"open"`). `"closed"` makes a Redis-backed throttle deny requests while degraded instead of falling back to the per-pod in-memory window — for hard upstream limits where the per-pod multiplier (N pods → N× the global limit during an outage) is unacceptable. Emits `throttle.fail_closed`. New ADR-0013. (Lane B #B8)

### Changed

- `AuditBackend` protocol restored to its locked LLD §2 shape: `health_check()` now returns a `HealthSnapshot` (not a bare `bool`) and a single-event `write()` is back alongside `write_many()`. The `bool` return was a latent crash — the `/readyz` aggregator reads `.healthy` on every snapshot, so an audit backend registered for recovery would have raised `AttributeError`. All three kit backends (noop, stdlib_logging, postgres) updated. (Lane B #B4)
- `BreakerConfig.excluded_exceptions` now defaults to `(ValueError, TypeError, KeyError, AttributeError, AssertionError)` instead of `()`. These caller/programmer errors no longer trip a transport-failure breaker — a `ValueError` from business logic kept legitimate traffic flowing instead of forcing the circuit OPEN. Overridable per service; the registry falls back to this set only when no override is supplied. (Lane B #B3)
- Classifier `Development Status :: 3 - Alpha` → `4 - Beta` — the surface has a locked API, a migration guide, two adopter dogfood reports, and Trusted Publishing. (Lane A #A4)
- `DefaultRedactor.DEFAULT_FIELDS` now redacts `cookie` / `set-cookie` by default — session cookies are auth-bearing (CWE-532). (Lane A #A1)
- `settings.audit.redact_fields` default now mirrors `DefaultRedactor.DEFAULT_FIELDS` (adds `api_key`, `x-api-key`, `cookie`, `set-cookie`); the wired default was silently narrower than the code default, under-redacting those keys. (Lane C #C5)
- Sliding-window throttle Lua uses a deterministic `INCR` counter for ZSET member ids instead of `math.random`, fixing non-determinism that Redis < 7 rejects. (Lane A #A9)
- Throttle Lua now reads `now` server-side via `redis.call('TIME')` instead of the client clock. Two pods with NTP drift previously computed different window cutoffs against the same sorted set, silently over- or under-throttling the fleet. Scripts declare `redis.replicate_commands()` for Redis < 7 (no-op on Redis 7+ / Valkey 8); `THROTTLE_LUA_VERSION` bumped `v2` → `v3`. (Lane B #B5)

### Fixed

- Django DRF throttles now work under ASGI (Daphne / Uvicorn). `_KitThrottle.allow_request` bridged the async throttle check with `asyncio.run`, which raises `RuntimeError: asyncio.run() cannot be called from a running event loop` under ASGI — every kit-throttled DRF route 500'd. Checks now route onto the adapter's persistent daemon loop via `run_coroutine_threadsafe` (`adapters/django/_bridge.run_on_kit_loop`, fed by the new `apps.get_kit_loop()`), which works from both WSGI (sync) and ASGI (running-loop) callers. ADR-0011 amended. (Lane C #C6)
- `PostgresAuditBackend._ensure_pool` now guards pool creation with an `asyncio.Lock` instead of a `threading.Lock`. A `threading.Lock` is released the instant `await` suspends, so concurrent first writes (from `FireAndForgetDispatcher`) could both create a pool and leak the orphan. (Lane B #B7)
- `cache.provider.get_cache()` no longer crashes. The `memory` entry point resolves to `InMemoryAsyncCache` directly (shadowing the `_build_memory` adapter), which was then called with an `alias` kwarg it did not accept. `InMemoryAsyncCache.__init__` now accepts and ignores `alias`, matching the adapter's contract. Surfaced by the new dead-symbol gate (#A14); the function had no caller. Added a provider unit test.

### Security

- Field crypto now uses a directly-supplied Fernet key as-is instead of always running it through unsalted SHA-256. If `crypto.field_encryption_key` is a valid Fernet key (`Fernet.generate_key()`), it is used directly; a passphrase still works via the (now deprecated, one-time-warned) SHA-256 path so existing ciphertext stays decryptable — the derivation is byte-for-byte unchanged. Added a settings validator that warns on short passphrases. Salted-KDF + rotation (`MultiFernet`) land in Lane C #C1. CWE-916. (Lane B #B6)
- `pinned_httpx_client()` now forces `follow_redirects=False` and raises `ValueError` if a caller passes `follow_redirects=True`. Auto-followed 3xx redirects resolved the new host through normal DNS — never re-validated against SSRF, never re-pinned — so an open redirect to `http://169.254.169.254/` (cloud metadata) or an internal IP bypassed the DNS pin entirely (CWE-918 + CWE-601). Callers needing redirects must follow them manually and call `resolve_and_validate()` per hop. (Lane B #B1)
- Bumped vulnerable locked dependencies flagged by the new `pip-audit` (OSV) gate: `cryptography` 48.0.0 → 49.0.0 (GHSA-537c-gmf6-5ccf), `pydantic-settings` 2.14.1 → 2.14.2 (GHSA-4xgf-cpjx-pc3j), `starlette` 1.2.1 → 1.3.1 (PYSEC-2026-248/249). Lockfile only; no API change.

### Removed

- Six unreachable `async def __acall__` methods in the Django adapter middleware — Django has no `__acall__` dispatch hook. (Lane A #A2)

### Documentation

- Amended ADR-0009 prose to match the implemented (and ADR-0004) resolution order: third-party entry points shadow same-named kit builtins. Added a contract test proving it. (Lane A #A3)

## [0.1.0] - 2026-06-11

First public stable release. Pinned by both reference boilerplates (`fastapi_boilerplate`, `django_boilerplate`) post-M7 migration. Builds on `0.1.0rc1` with the §3.1 pre-cut ergonomics bundle (D1 helpers A–E) that closes every M7 dogfooding finding flagged as high-severity. Surface is additive — `rc1` users upgrade with a pin bump unless they hit the blocker recipes documented in [`docs/MIGRATION-rc1-to-v0.1.0.md`](./docs/MIGRATION-rc1-to-v0.1.0.md).

### Added

- `.github/workflows/release.yml` — tag-driven release pipeline. Pushing a `v*` tag triggers: tag↔`_version.py` consistency check, `uv build` of sdist + wheel, `twine check --strict`, a smoke-import of the built wheel in a clean venv, PyPI publish via Trusted Publishing (no token in secrets), and a GitHub Release with notes extracted from this CHANGELOG. Pre-release tags (`*rc*` / `*a*` / `*b*` / `*dev*`) get the GitHub `--prerelease` flag automatically. **Requires a one-time PyPI Trusted Publisher configuration** at <https://pypi.org/manage/account/publishing/> (repo `prajwalmahajan101/resilience-kit`, workflow `release.yml`, environment `pypi`).
- `resilience_kit.context.bind_to(target)` — context manager that mirrors `resilience_kit.context.request_id` into a consumer-owned `ContextVar`. Lets a boilerplate that keeps its own `request_id_ctx` receive the value the kit's middleware seeded without rewriting its own context layer. Closes the M7 FastAPI dogfooding finding (kit-set `request_id` was `null` in the boilerplate's own logging / envelope paths). See MIGRATION §10.3.
- `resilience_kit.testing.reset_all_singletons_async()` — async ergonomic shim around `reset_all_singletons()`. The underlying reset is non-blocking; this wrapper exists so async test harnesses (`pytest-asyncio`, `pytest-trio`) can `await` it inline instead of routing through `asyncio.to_thread`.
- `resilience_kit.testing.verify_envelope_contract(handler, envelope_schema, exceptions=...)` — pytest helper that exercises every HTTP-reachable kit exception through an adopter's handler + envelope schema and collects every failure into a single `AssertionError`. Lets a project that layers its own exception handler on top of (or in place of) the kit's prove, in their own test suite, that the resulting wire shape stays valid for every kit exception class. Closes Django dogfooding §3.6 untested-bridge finding.
- `resilience_kit.adapters._envelope.from_exception(exc, *, envelope_cls=None, extra_headers=None)` — framework-agnostic envelope builder. Returns `(body, status, headers)` for any `ResilienceKitError`. When `envelope_cls` (a pydantic model) is supplied, the body is projected onto the consumer's chosen field aliases (`error_code | code | error`, `message | detail`, `details` dict or `errors` list, plus optional `request_id` and `success` flags). The FastAPI and Django adapters now delegate their envelope construction to this helper — wire shape is unchanged. Closes the M7 FastAPI two-envelope finding by giving consumers a one-call way to re-wrap kit exceptions into their own envelope. See MIGRATION §10.1 / §10.2.
- `resilience_kit.runtime.legacy_env_alias(env=None, aliases=DEFAULT_ALIASES, warn=True)` + `DEFAULT_ALIASES` — opt-in translator that copies legacy boilerplate env-var values (`FIELD_ENCRYPTION_KEY`, `RATE_LIMIT_*`, `CIRCUIT_BREAKER_*`, `REDIS_URL`, …) onto their `RESILIENCE_*` equivalents and emits a `DeprecationWarning`. The kit-prefixed name always wins on collision. Call once at the top of the settings module before `ResilienceSettings()` instantiates. Closes the Django dogfooding §3.3 deploy-time risk (silent tuning loss on the next prod deploy). See MIGRATION §10.5.

### Changed (breaking inside 0.1.x)

- `ResilienceSettings` now uses `extra="forbid"` at the model root: unknown top-level keys in dict-shaped inputs (Django `settings.RESILIENCE = {...}`, programmatic `model_validate(...)`, JSON configs) raise `pydantic.ValidationError` instead of being silently dropped. Catches the legacy-key footgun (`CIRCUIT_BREAKER_CONFIG`, `RATE_LIMIT_CONFIG`, `FIELD_ENCRYPTION_KEY`) that the M7 boilerplate migration was about to import verbatim. Strictness on unknown `RESILIENCE_*` env vars is **not** included — pydantic-settings filters them at the source layer; tracked as a follow-up.

### Fixed

- `EncryptedCharField.from_db_value` (Django adapter) and `EncryptedString.process_result_value` (FastAPI/SQLAlchemy adapter) now coerce `bytes` / `bytearray` inputs to `str` before handing them to `FernetCipher.decrypt`. Previously a `bytes` cipher round-trip from a custom driver, raw query, or non-default encoding raised `AttributeError` inside `FernetCipher.decrypt` (which calls `.encode("ascii")`). `None` and `str` continue to pass through unchanged. ISSUE-003.

### Documentation

- `_providers.py` docstring and `docs/LLD.md` §3 now document that third-party entry points shadow same-named kit builtins by design (drop-in replacement use case) and that this is a footgun for accidental name collisions — operators should namespace third-party backend names. Cross-linked from [ADR 0004](./docs/adr/0004-entry-points-for-third-party-backends.md). ISSUE-005.
- `pyproject.toml`: the empty `[project.entry-points."resilience_kit.settings_sources"]` group now carries an inline comment explaining it is an intentional extension hook (LLD §3) so a future "remove dead config" pass doesn't strip it. ISSUE-004.

### Documentation — M7 dogfooding patterns (no behavior change)

- `docs/MIGRATION-from-boilerplate-embedded.md` §10 — new "Patterns from the M7 dogfooding reports" section covering the four traps the FastAPI + Django boilerplate migrations hit on the fly: the `BaseCustomError(ResilienceKitError)` exception-bridge pattern, the two-handler envelope-collision footgun, request-id `ContextVar` interop, the provider-API rename table, and the operator env-var translation table. **Operator action required before promoting any v0.1.0 migration past staging** — audit every `.env*` file against the env-var translation table in §10.5; the kit does not read the legacy `RATE_LIMIT_*` / `CIRCUIT_BREAKER_*` / `FIELD_ENCRYPTION_KEY` names.
- `adapters/fastapi.exception_handlers.install` and `adapters/django.exception_handler.handle` docstrings now warn that installing the kit handlers alongside a project's own exception handlers can silently change the wire shape for kit-raised exceptions (the M7 FastAPI report §0.2 footgun) and cross-link the migration-doc remediation.

## [0.1.0rc1] - 2026-06-10

First public release candidate. Cut to PyPI as a packaging smoke-test before the M7 boilerplate migration. Pre-release per [PEP 440](https://peps.python.org/pep-0440/) — `pip` will not install it without an explicit version pin or `--pre`. The 0.1.0 final ships at M8b after both boilerplates depend on the kit.

### Added

- Top-level re-exports of `http_status_for` and `HTTP_STATUS_MAP` (the LLD §11 exception↔HTTP mapping). Adapters and callers no longer need to reach into `resilience_kit.exceptions` for the locked-contract status table.

<!-- m5-placeholder: feat/m5-fastapi-adapter replaces this line -->
- M5: FastAPI adapter (`resilience_kit.adapters.fastapi`).
  - `resilience_lifespan(inner=None)` — factory returning a FastAPI lifespan that starts `recovery.monitor` on enter and drains the audit dispatcher + stops the monitor on exit. Composes with an optional inner lifespan.
  - `install_health_routes(app)` — mounts `GET /healthz` (always 200) and `GET /readyz` (reads `health_snapshot`, propagates 200 / 503). Excluded from the OpenAPI schema.
  - `install_exception_handlers(app)` — maps every `ResilienceKitError` to the LLD §11 envelope via `exceptions.http_status_for`; `RateLimitError` gets a dedicated handler so the 429 response carries `Retry-After` + `X-RateLimit-*` headers without an extra branch.
  - `install_middleware_stack(app, **opts)` — mounts the kit's six ASGI middleware in the LLD §11 outer→inner order. `SelectiveCorsMiddleware` is only added when both `cors_allow_origins` and `cors_path_prefixes` are passed so apps that handle CORS upstream are never double-wrapped.
  - `rate_limit(scope, rate, *, attr_from_request=None)` — FastAPI dependency factory backed by `throttle.provider.get_throttle`. Parses the rate spec once at build time; raises `RateLimitError` on deny.
  - `request_id_dep()` — returns the active `request_id` ContextVar.
  - `EncryptedString` — SQLAlchemy 2.x `TypeDecorator[str]` over `FernetCipher`; `cache_ok = True`. None passes through.
  - `[fastapi]` extra now pulls `sqlalchemy>=2.0` and `httpx>=0.27,<0.29` so a single `pip install resilience-kit[fastapi]` wires the whole adapter.
  - `tests/integration/fastapi_app/` — minimal example + e2e suite against `testcontainers[postgresql]`. Asserts the M5 exit gate: health routes serve 200, 3rd `/limited` returns 429 with `Retry-After`, `EncryptedString` round-trips (Fernet token on disk, plaintext through the ORM), `AsyncAPIClient` reaches a fake upstream via injected transport.
  - ADR 0010 (FastAPI adapter shape).
<!-- m6-placeholder: feat/m6-django-adapter replaces this line -->
- M6: Django adapter (`resilience_kit.adapters.django`).
  - `ResilienceConfig` AppConfig — reads `settings.RESILIENCE['services']`, registers each per-service override, and spawns a daemon thread that owns a private asyncio loop driving `recovery.monitor` for the worker lifetime. atexit hook drains the audit dispatcher + stops the monitor on graceful exit. Idempotent across Django's autoreloader.
  - Six middleware classes mirroring the kit's ASGI stack — `RequestIdMiddleware`, `BodyLimitMiddleware`, `SecurityHeadersMiddleware`, `SelectiveCorsMiddleware`, `RateLimitHeadersMiddleware`, `ExceptionLoggingMiddleware`. Both `sync_capable` + `async_capable`; the last two implement `process_exception` so view-raised kit errors are caught regardless of WSGI / ASGI mode.
  - Five DRF throttle classes — `IPThrottle`, `UserTierThrottle`, `EndpointThrottle`, `BurstThrottle`, `AuthThrottle`. Subclass `BaseThrottle`, derive scope-specific keys via `throttle.scopes.build_key`, delegate to `throttle.provider.get_throttle()`. Rates resolve from `RESILIENCE_THROTTLE_RATES` (Django setting), with per-scope defaults. Deny raises `RateLimitError` so the response carries the LLD §11 envelope + the canonical `X-RateLimit-*` headers rather than DRF's `Throttled` shape.
  - `handle(exc, context)` DRF exception handler — install via `REST_FRAMEWORK['EXCEPTION_HANDLER']`. Maps every `ResilienceKitError` through `exceptions.http_status_for`; non-kit exceptions fall through to DRF's default handler.
  - `EncryptedCharField` — Django model field mirroring the FastAPI adapter's `EncryptedString`. `get_prep_value` + `from_db_value` over `FernetCipher`. Default `max_length=512`. `None` passes through.
  - Management commands — `resilience_status` (with `--json`) prints overall + per-backend + per-service breaker state; `resilience_reset <service|--all>` force-closes breakers.
  - `tests/integration/django_app/` — minimal Django + DRF project + e2e suite against `testcontainers postgres:16`. Asserts the M6 exit gate: middleware echoes X-Request-Id + X-Content-Type-Options; IPThrottle('2/min') denies the 3rd request with the LLD §11 envelope + Retry-After + X-RateLimit-Limit=2; EncryptedCharField round-trips (Fernet token on disk, plaintext through the ORM); management commands run.
  - `[dependency-groups] test-integration` gains `pytest-django` + `psycopg[binary]`.
  - `docs/sync-vs-async.md` + ADR 0011 (Django sync/async bridge).

- M4: Audit + middleware + metrics + entry-point wiring.
  - `resilience_kit.dispatch.fire_and_forget` — shared bounded queue + background worker + graceful drain. Drop-newest (default) / drop-oldest overflow with `dispatch.dropped` metric. Worker spawned in `contextvars.copy_context()` to isolate per-request pins.
  - `resilience_kit.health.health_snapshot()` — `/readyz` aggregator that walks `recovery.registered_backends()`, runs `health_check()` in parallel with per-probe timeout, and reduces to `ok` / `degraded_but_serving` / `degraded` with the matching Kubernetes-style HTTP status.
  - `resilience_kit.metrics.get_metrics()` — settings-driven sink factory. Builtins `noop` and `stdlib_logging` published as entry points; unknown sink names log a warning and fall back to no-op so observability misconfiguration cannot crash the kit.
  - `resilience_kit.audit` — full subsystem: `AuditEvent` (LLD §7 shape), `AuditBackend` protocol, `NoopAuditBackend` + `StdlibLoggingAuditBackend` builtins, `PostgresAuditBackend` (asyncpg + batched executemany; extra `[audit-postgres]`). `Sanitizer` protocol + `DefaultRedactor` deep-walking dicts/lists. `FireAndForgetDispatcher` (LLD §7: bounded queue + batched flush + backend retry x3 + stdlib_logging fallback) and `InlineDispatcher` (tests). `@log_inbound` / `@log_outbound` decorators capturing timing, outcome, error class+code, and ContextVar request_id / correlation_id; optional `payload_factory` extracts the audit payload from call args.
  - `resilience_kit.middleware` — framework-agnostic ASGI middleware: `RequestIdMiddleware` (seeds + echoes request_id / correlation_id), `BodyLimitMiddleware` (413 on oversize Content-Length or streamed body), `SecurityHeadersMiddleware` (conservative default header set + overrides/extras), `SelectiveCorsMiddleware` (CORS only on configured path prefixes), `RateLimitHeadersMiddleware` (catches `RateLimitError` → canonical 429 + `X-RateLimit-*`), `ExceptionLoggingMiddleware` (maps every kit exception onto its locked LLD §11 HTTP status + `{error_code,message,details}` envelope; non-kit raises become a generic 500 with no stack leakage).
  - `resilience_kit.tasks` — in-process fire-and-forget task queue on top of `dispatch.fire_and_forget`. `register(name)` decorator + `submit(name, *args, **kwargs)` API; missing handler raises at submit time, handler failures are logged + metered via `tasks.failed` without breaking the worker.
  - `AsyncAPIClient` now routes its default `on_outbound` audit through `audit.get_dispatcher()` — caller-supplied callbacks still win.
  - Entry-point discovery: every kit-shipped builtin is also published under the kit's groups (`resilience_kit.{cache,breaker,throttle,audit,metrics}_*`) so the provider chain has one shape end-to-end. `tests/fixtures/fake_third_party/` proves the chain via `tests/contract/test_provider_chain.py` (installs the fixture with `uv pip install -e`, asserts `_providers.resolve_provider` finds it).
  - `tests/integration/test_audit_postgres.py` — testcontainers Postgres + `@log_outbound` lands a sanitized row in `resilience_kit_audit`. `tests/integration/test_readyz_degraded.py` — paused redis container → `health_snapshot()` reports non-OK.
  - Top-level re-exports: `log_inbound`, `log_outbound`, `AuditEvent`, `health_snapshot`, `HealthAggregate`, `HealthStatus`.
  - `testing.reset_all_singletons` now clears the audit dispatcher, tasks queue, and tasks-handler registry so pytest-asyncio per-test loops don't bind queues to closed loops.
  - ADRs: 0005 (fire-and-forget audit), 0009 (entry-point precedence chain).

- M3: HTTP client + SSRF + crypto.
  - `resilience_kit.ssrf` — `resolve_and_validate(url, strict=)`, `assert_public_url`, `assert_allowed_url`. Rejects non-http(s), private / loopback / link-local / multicast / reserved / unspecified addresses; allow-list supports exact host and `.suffix` matching.
  - `resilience_kit.http_client` — `AsyncAPIClient(service)` composes `resolve_and_validate → assert_allowed_url → pinned(host→ips) → @resilient(service) → httpx.AsyncClient.request → map_httpx_errors → on_outbound audit hook` (LLD §5). Verb shortcuts (`get` / `post` / `put` / `patch` / `delete`). Sync mirror `request_sync` drives a private event loop only when no loop is running; raises `RuntimeError` from inside a running loop.
  - `PinnedHTTPTransport` — `httpx.AsyncHTTPTransport` subclass that reads `pinned_dns` ContextVar and rewrites the request URL host to the pinned IP, preserving `Host` header + TLS SNI for cert verification.
  - `pinned(host_to_ips)` context manager — token-restoring ContextVar set/reset; isolates DNS pins per asyncio task (LLD §9).
  - Auth helpers — `BearerAuth`, `BasicAuth`, `HMACAuth` (HMAC-SHA256 over `METHOD\nPATH\nTS\nBODY`, with optional `X-Signature-Key-Id`).
  - `pinned_httpx_client(**kwargs)` and `pinned_requests_session()` factories — extras-gated; raise `MissingExtraError` at import / first call when the optional dep is missing.
  - `resilience_kit.crypto.FernetCipher.encrypt/decrypt` — SHA-256-of-secret key derivation, `lru_cache(maxsize=1)` instance. `settings.crypto.environment="prod"` refuses to start without `field_encryption_key`; `"dev"` / `"test"` fall back to an insecure-on-purpose constant with a one-time warning. Wrong key / corrupted token raises `DecryptionError`.
  - `CryptoSettings.environment: Literal["prod","dev","test"]` field on `ResilienceSettings`.
  - Exit-gate tests: TOCTOU DNS-rebinding under `tests/integration/test_dns_rebinding.py`; Fernet round-trip + prod-without-key refusal under `tests/unit/crypto/test_fernet.py`.
  - Contract suite additions for SSRF allow-list shapes and httpx error mapping.
  - `resilience_kit.__init__` re-exports `AsyncAPIClient`, `pinned`, `FernetCipher` via lazy `__getattr__` so `import resilience_kit` does not require the `[http]` / `[crypto]` extras.
  - `.importlinter` extended with the L3 modules; `testing.reset_all_singletons` now clears the Fernet cache.
  - ADRs: 0007 (DNS pin via ContextVar), 0008 (Fernet env-guard).

- M2: Redis / Valkey + pybreaker backends.
  - Shared provider-resolution chain (`resilience_kit._providers.resolve_provider`) implementing LLD §3: explicit → importable string → entry point → builtin → `UnknownBackendError` with the list of options.
  - `PyBreakerAsyncBreaker` — async wrapper over the synchronous `pybreaker` library using `CircuitBreaker.calling()` so the contextmanager protocol lets the breaker observe both sync and async upstreams.
  - `RedisAsyncBreaker` — Redis/Valkey-backed breaker with an atomic Lua state machine (CLOSED ↔ OPEN ↔ HALF_OPEN in one EVALSHA). Fail-open delegation to `InMemoryAsyncBreaker` on any Redis error, self-registers with the recovery monitor, `NoScriptError` triggers script reload.
  - `RedisAsyncThrottle` — sliding-window Lua + in-call recovery probe (30 s gate so quiet workers don't keep PINGing). Fail-open to memory throttle.
  - `RedisAsyncCache` — plain Redis ops, fail-open for everything except `incr` (which raises rather than diverge on the authoritative counter).
  - `RecoveryMonitor` singleton — settings-driven probe interval (default 10 s production, tunable to 0.2 s in tests), warm hooks fire after any backend recovers, graceful start/stop from adapters.
  - `MissingExtraError` raised at module-import time for every backend gated behind a pip extra. The error message carries the exact `pip install` hint.
  - `auto` backend picker — chooses `redis` when `RESILIENCE_REDIS_URL` is set + the extra is importable, else `memory`.
  - Contract suite parametrized over `memory + pybreaker + redis` with testcontainers-backed Redis. Backend-N/A combinations (e.g. FakeClock + Redis TTL) skip cleanly.
  - Integration test proving the ROADMAP M2 exit gate: paused container → fail-open → unpause → recovery in < 5 s.

### Fixed

- `reset_settings_cache` now restores the default `EnvSettingsSource` so tests that swap in a `FixedSource` don't leak it into following tests.

- M1: core primitives, in-memory only.
  - Public decorators: `@retry`, `@retry_on_failure(name)`, `@circuit_breaker(name)`, `@resilient(name)` — sync + async, breaker-outer / retry-inner composition.
  - Per-service `ResilienceRegistry` with defaults overlay and cached breaker instances.
  - Exception hierarchy with stable `error_code` and structured `details`: `TransientError`, `ExternalTimeoutError`, `ExternalServiceError`, `ServiceUnavailableError`, `RepositoryError`, `DecryptionError`, `MissingExtraError`, `UnknownBackendError`, `ValidationError`, `RateLimitError` (with `response_headers()`).
  - `ResilienceSettings` (pydantic v2) loaded from env via `RESILIENCE_*`, plus pluggable `SettingsSource` indirection.
  - `request_id` / `correlation_id` ContextVars (LLD §9).
  - Protocols: `AsyncBreaker`, `AsyncThrottle`, `AsyncCache`, `MetricsSink`, `Clock`, `SettingsSource` (LLD §2, locked at v0.1).
  - In-memory backends for breaker (state machine with fake-clock support), throttle (sliding-window deque), cache (TTL + lazy eviction, atomic `incr`).
  - Throttle scope keys: `IP`, `ENDPOINT`, `USER_TIER`, `GLOBAL`, `BURST`, `AUTH`; `Rate.parse("60/min")` parser.
  - `MetricsSink` protocol with `NoopMetricsSink` (default) and `StdlibLoggingMetricsSink`.
  - Decorrelated-jitter, exponential, and constant backoff strategies; jitter selectable via settings.
  - Testing helpers: `FakeClock`, `FakeAuditSink`, `reset_all_singletons`.
  - Contract test suite parametrized over backends — currently `memory` only; M2 wires `redis` and `pybreaker`.
  - Activated full layered-architecture contract in `.importlinter`.
- M0: repo scaffold — `pyproject.toml` with extras matrix, source layout with `py.typed`, ruff + mypy + import-linter + pydocstyle + darglint configs, pre-commit, GitHub Actions CI (lint / types / imports / tests on Python 3.11–3.13), CodeQL workflow, PR template, CODEOWNERS, dependabot, issue templates, smoke test.

[Unreleased]: https://github.com/prajwalmahajan101/resilience-kit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/prajwalmahajan101/resilience-kit/compare/v0.1.0rc1...v0.1.0
[0.1.0rc1]: https://github.com/prajwalmahajan101/resilience-kit/releases/tag/v0.1.0rc1
