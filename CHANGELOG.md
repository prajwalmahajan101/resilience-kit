# Changelog

All notable changes to `prajwal-resilience-kit` are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
