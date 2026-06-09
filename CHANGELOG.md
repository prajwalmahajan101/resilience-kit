# Changelog

All notable changes to `prajwal-resilience-kit` are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

[Unreleased]: https://github.com/prajwalmahajan101/resilience-kit/compare/...HEAD
