# Directory tree — `resilience-kit` v0.1

Final shape of the repo at v0.1.0 release. Items marked `[Mx]` arrive in that milestone (see [ROADMAP.md](./ROADMAP.md)). Items marked `(extra)` only get installed when the matching pip extra is requested.

```
resilience-kit/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                          # [M0] lint + types + tests, py 3.11/3.12/3.13
│   │   ├── integration.yml                 # [M2] testcontainers job (redis:7 + valkey:8)
│   │   ├── release.yml                     # [M8] tag → build → trusted-publish to PyPI
│   │   └── codeql.yml                      # [M0] static analysis
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── CODEOWNERS
│   └── dependabot.yml
│
├── .gitignore                              # [M0] ✓ exists
├── .pre-commit-config.yaml                 # [M0] ruff, mypy, pydocstyle, darglint, eof
├── .python-version                         # [M0] uv pin (3.12)
├── LICENSE                                 # [M0] ✓ exists (MIT)
├── README.md                               # [M0] ✓ exists
├── CHANGELOG.md                            # [M0] Keep-a-Changelog
├── pyproject.toml                          # [M0] uv-managed, extras matrix, entry-point groups
├── uv.lock                                 # [M0] checked in
├── ruff.toml                               # [M0] lint + format config
├── mypy.ini                                # [M0] --strict
├── importlinter.cfg                        # [M0] enforces L0–L4 layer rules from LLD §1
│
├── docs/
│   ├── PRD.md                              # ✓ exists — product requirements
│   ├── ROADMAP.md                          # ✓ exists — milestones & features
│   ├── LLD.md                              # ✓ exists — low-level design
│   ├── DIRECTORY-TREE.md                   # ✓ exists — this file
│   ├── ARCHITECTURE.md                     # [M1] one-pager: layering + provider chain
│   ├── sync-vs-async.md                    # [M6] sync→async rules for Django adapter
│   ├── MIGRATION-from-boilerplate-embedded.md  # [M7] for boilerplate migrators
│   ├── SECURITY.md                         # [M8] vuln reporting policy
│   ├── CONTRIBUTING.md                     # [M8] dev setup + add-a-backend guide
│   └── adr/                                # [M1] architecture decision records
│       ├── 0001-protocol-not-abc.md
│       ├── 0002-handrolled-retry-not-tenacity.md
│       ├── 0003-single-package-with-extras.md
│       ├── 0004-entry-points-for-third-party-backends.md
│       ├── 0005-fire-and-forget-audit.md
│       ├── 0006-outer-breaker-inner-retry.md
│       ├── 0007-dns-pin-via-contextvar.md
│       ├── 0008-fernet-env-guard.md
│       ├── 0009-entry-point-precedence-chain.md
│       ├── 0010-fastapi-adapter-shape.md
│       ├── 0011-django-sync-async-bridge.md
│       ├── 0012-idempotency-key-on-retried-writes.md  # [v0.1.1] Lane B #B2
│       └── 0013-throttle-fail-mode.md      # [v0.1.1] Lane B #B8
│
├── src/
│   └── resilience_kit/
│       ├── __init__.py                     # [M1] re-exports: resilient, circuit_breaker,
│       │                                   #        retry, retry_on_failure, registry
│       ├── py.typed                        # [M0] PEP 561 marker
│       ├── _version.py                     # [M0] single source of truth for __version__
│       ├── _providers.py                   # [M2] shared resolve_provider() helper (LLD §3)
│       │
│       ├── runtime.py                      # [M1] get_settings(), require(), SettingsSource
│       ├── settings.py                     # [M1] ResilienceSettings (pydantic v2) (LLD §10)
│       ├── context.py                      # [M1] request_id, correlation_id ContextVars
│       ├── registry.py                     # [M1] per-service config + health snapshot
│       ├── decorators.py                   # [M1] @circuit_breaker, @resilient
│       ├── recovery.py                     # [M2] background backend re-prober
│       ├── health.py                       # [M4] /readyz aggregator helpers
│       ├── metrics.py                      # [M4] MetricsSink protocol + noop/stdlib sinks
│       │
│       ├── exceptions/                     # [M1]
│       │   ├── __init__.py                 #         re-exports
│       │   ├── base.py                     #         ResilienceKitError root
│       │   ├── infrastructure.py           #         ExternalServiceError, Timeout,
│       │   │                               #           ServiceUnavailableError, Repository,
│       │   │                               #           Transient, MissingExtraError,
│       │   │                               #           UnknownBackendError
│       │   └── validation.py               #         ValidationError, RateLimitError
│       │
│       ├── retry/                          # [M1]
│       │   ├── __init__.py
│       │   ├── decorator.py                #         @retry, @retry_on_failure (sync+async)
│       │   └── backoff.py                  #         constant/exp/decorrelated jitter
│       │
│       ├── circuit_breaker/
│       │   ├── __init__.py                 # [M1]
│       │   ├── base.py                     # [M1]  AsyncBreaker protocol, BreakerState
│       │   ├── memory_impl.py              # [M1]  default
│       │   ├── pybreaker_impl.py           # [M2]  (extra: pybreaker)
│       │   ├── redis_impl.py               # [M2]  atomic Lua state machine (extra: redis)
│       │   ├── lua_scripts.py              # [M2]  breaker.lua + SHA registry
│       │   └── provider.py                 # [M1]  uses _providers.resolve_provider
│       │
│       ├── throttle/
│       │   ├── __init__.py                 # [M1]
│       │   ├── base.py                     # [M1]  AsyncThrottle, Rate, ThrottleDecision
│       │   ├── scopes.py                   # [M1]  ip/endpoint/user_tier/global/burst/auth
│       │   ├── memory_impl.py              # [M1]
│       │   ├── redis_impl.py               # [M2]  (extra: redis)
│       │   ├── lua_scripts.py              # [M2]  token_bucket.lua + sliding_window.lua
│       │   └── provider.py                 # [M1]
│       │
│       ├── cache/
│       │   ├── __init__.py                 # [M1]
│       │   ├── base.py                     # [M1]  AsyncCache protocol
│       │   ├── memory_impl.py              # [M1]
│       │   ├── redis_impl.py               # [M2]  (extra: redis)
│       │   └── provider.py                 # [M1]
│       │
│       ├── ssrf/                           # [M3]
│       │   ├── __init__.py
│       │   ├── guard.py                    #         resolve_and_validate, allow-list
│       │   └── _ipchecks.py                #         private/loopback/etc rules
│       │
│       ├── http_client/                    # [M3] (extra: http)
│       │   ├── __init__.py                 #         re-exports AsyncAPIClient
│       │   ├── client.py                   #         composes ssrf+breaker+retry+audit
│       │   ├── session.py                  #         pinned_httpx_client, pinned_requests
│       │   ├── dns_pin.py                  #         ContextVar pin + httpx resolver hook
│       │   ├── auth.py                     #         Bearer/Basic/HMAC
│       │   └── errors.py                   #         request/response error normalization
│       │
│       ├── crypto/                         # [M3] (extra: crypto)
│       │   ├── __init__.py                 #         re-exports FernetCipher
│       │   ├── fernet.py                   #         encrypt/decrypt with env-guarded key
│       │   └── exceptions.py               #         FernetUnavailable, EncryptionConfig
│       │
│       ├── audit/                          # [M4]
│       │   ├── __init__.py                 #         re-exports log_inbound, log_outbound
│       │   ├── decorators.py               #         @log_inbound, @log_outbound
│       │   ├── dispatch.py                 #         fire-and-forget + inline dispatchers
│       │   ├── sanitizers.py               #         field redactor (Sanitizer protocol)
│       │   ├── factory.py                  #         build from settings
│       │   └── backends/
│       │       ├── __init__.py
│       │       ├── base.py                 #         AuditBackend protocol, AuditEvent
│       │       ├── noop.py                 #         default
│       │       ├── stdlib_logging.py       #         default
│       │       └── postgres.py             #         (extra: audit-postgres) asyncpg
│       │
│       ├── middleware/                     # [M4]
│       │   ├── __init__.py
│       │   ├── request_id.py
│       │   ├── body_limit.py
│       │   ├── security_headers.py
│       │   ├── selective_cors.py
│       │   ├── rate_limit_headers.py
│       │   └── exception_logging.py
│       │
│       ├── tasks/                          # [M4]
│       │   ├── __init__.py
│       │   ├── queue.py                    #         bounded in-process queue, drain on shutdown
│       │   └── registry.py
│       │
│       ├── dispatch/                       # [M4]
│       │   ├── __init__.py
│       │   └── fire_and_forget.py          #         shared by audit + tasks
│       │
│       ├── utils/                          # small framework-agnostic helpers
│       │   ├── __init__.py
│       │   ├── log_sanitization.py         # [M4]
│       │   ├── function_logger.py          # [M4]
│       │   ├── network.py                  # [M4]   IP parsing, trusted-proxy resolution
│       │   ├── timing.py                   # [M4]
│       │   └── data.py                     # [M4]   deep-merge, frozen helpers
│       │
│       ├── testing/                        # [M1]
│       │   ├── __init__.py                 #         re-exports
│       │   ├── reset.py                    #         reset_all_singletons()
│       │   ├── fakes.py                    #         FakeClock, FakeRedis, FakeAuditSink
│       │   └── fixtures.py                 #         pytest fixtures for reuse
│       │
│       └── adapters/
│           ├── __init__.py
│           ├── django/                     # [M6] (extra: django)
│           │   ├── __init__.py
│           │   ├── apps.py                 #         AppConfig
│           │   ├── settings_source.py      #         DjangoSettingsSource
│           │   ├── middleware.py           #         WSGI/ASGI wrappers
│           │   ├── drf_throttles.py        #         IP/UserTier/Endpoint/Burst/Auth
│           │   ├── exception_handler.py    #         DRF handler
│           │   ├── fields.py               #         EncryptedCharField
│           │   └── management/
│           │       ├── __init__.py
│           │       └── commands/
│           │           ├── __init__.py
│           │           ├── resilience_status.py
│           │           └── resilience_reset.py
│           │
│           └── fastapi/                    # [M5] (extra: fastapi)
│               ├── __init__.py
│               ├── lifespan.py             #         @asynccontextmanager
│               ├── settings_source.py      #         optional pydantic-settings adapter
│               ├── middleware.py           #         Starlette wrappers
│               ├── dependencies.py         #         rate_limit(scope, rate), request_id_dep
│               ├── exception_handlers.py   #         install(app)
│               └── fields.py               #         EncryptedString SQLAlchemy TypeDecorator
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                         # [M0] global fixtures (reset, clock, redis_url)
│   │
│   ├── unit/                               # [M1] one folder per src/ subpackage
│   │   ├── test_runtime.py
│   │   ├── test_registry.py
│   │   ├── test_decorators.py
│   │   ├── test_exceptions_mapping.py
│   │   ├── retry/
│   │   ├── circuit_breaker/
│   │   ├── throttle/
│   │   ├── cache/
│   │   ├── ssrf/
│   │   ├── crypto/
│   │   ├── audit/
│   │   ├── middleware/
│   │   └── utils/
│   │
│   ├── contract/                           # [M1] parametrized over backends
│   │   ├── __init__.py
│   │   ├── conftest.py                     # backend factory fixtures
│   │   ├── test_breaker_contract.py
│   │   ├── test_throttle_contract.py
│   │   ├── test_cache_contract.py
│   │   ├── test_retry_contract.py
│   │   ├── test_audit_backend_contract.py  # [M4]
│   │   └── test_provider_chain.py          # [M4] explicit → string → entry-point → builtin
│   │
│   ├── integration/                        # [M2+] real services via testcontainers
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_recovery_monitor.py        # [M2] kill + restart redis
│   │   ├── test_dns_rebinding_toctou.py    # [M3]
│   │   ├── test_audit_postgres.py          # [M4]
│   │   ├── fastapi_app/                    # [M5] full example app + e2e tests
│   │   │   ├── main.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   └── tests/
│   │   │       └── test_e2e.py
│   │   └── django_app/                     # [M6] full example app + e2e tests
│   │       ├── manage.py
│   │       ├── project/
│   │       │   ├── settings.py
│   │       │   ├── urls.py
│   │       │   └── wsgi.py
│   │       ├── demo/
│   │       │   ├── models.py
│   │       │   ├── views.py
│   │       │   └── apps.py
│   │       └── tests/
│   │           └── test_e2e.py
│   │
│   ├── fuzz/                               # [M3] hypothesis-driven
│   │   ├── test_rate_parse.py
│   │   ├── test_ssrf_urls.py
│   │   └── test_sanitizer.py
│   │
│   ├── perf/                               # [M2] pytest-benchmark
│   │   ├── test_breaker_overhead.py
│   │   ├── test_throttle_overhead.py
│   │   └── test_retry_overhead.py
│   │
│   └── fixtures/                           # [M4] installable mini-packages
│       └── fake_third_party/               #       proves entry-point discovery
│           ├── pyproject.toml              #       declares rk-cache + rk-audit entry points
│           └── fake_third_party/
│               ├── __init__.py
│               ├── cache.py
│               └── audit.py
│
└── scripts/
    ├── bench_compare.py                    # [M2] runs perf/, diffs against main
    ├── generate_lua_sha.py                 # [M2] dev helper
    └── verify_extras_matrix.py             # [M0] pip-install each extra in a clean venv
```

---

## File-count budget (informational)

| Layer | Files at v0.1.0 | Comment |
|---|---|---|
| `src/resilience_kit/` (core, no adapters, no tests) | ~75 | Most are one-class-per-file Python; keeps imports cheap and reviewable |
| `src/resilience_kit/adapters/` | ~20 | ≲ 500 LOC each adapter |
| `tests/` | ~100 | Heaviest under `unit/` and `integration/`; contract suite is small but parametrized |
| `docs/` | 11 + ADRs | Living docs |
| Root config | ~15 | pyproject, ruff, mypy, importlinter, pre-commit, CI workflows |

**Total**: ≲ 250 files. If we cross 350 we should consider splitting an adapter into its own package.

---

## Naming conventions

- **Modules**: `snake_case`, no abbreviations except `db`, `http`, `ssrf`, `dns`, `tls`.
- **Backend files**: `<backend>_impl.py` (e.g. `redis_impl.py`, `pybreaker_impl.py`) — keeps the protocol file (`base.py`) lexically first.
- **Provider files**: `provider.py` in every swappable subdirectory — the only public way callers obtain a backend.
- **Lua scripts**: `lua_scripts.py` (single module per subsystem) with versioned tags so `NoScriptError` reload works deterministically.
- **Tests**: `test_<unit_under_test>.py`. Contract tests start with `test_` and end with `_contract.py`.
- **Adapters**: every adapter file mirrors a kit file (`adapters/fastapi/middleware.py` ↔ `middleware/*.py`). One-to-one mapping makes drift obvious in PR review.
