# Migrating from embedded `core/resilience/` to `resilience-kit`

For maintainers of [`fastapi_boilerplate`](https://github.com/prajwalmahajan101/fastapi_boilerplate)
and [`django_boilerplate`](https://github.com/prajwalmahajan101/django_boilerplate) — and anyone
who copy-pasted the same `core/` layout into a third repo. This guide is the M7 deliverable
referenced in [ROADMAP.md](./ROADMAP.md).

The kit replaces the embedded `core/resilience/`, `core/api_log/`, the kit-owned middleware,
the SSRF guard, the Fernet helper, the metrics shim, and the lightweight infra utilities.
Domain code (auth, RBAC, ORM bases, response envelopes, OpenAPI) stays in the boilerplate —
the kit deliberately does not own it (see [PRD §6](./PRD.md#6-out-of-scope-v01)).

---

## 1. Install

During M7 (pre-PyPI), both boilerplates pin the `milestone/m7-rc1` tag:

**FastAPI** — `requirements/base.in`:

```text
resilience-kit[fastapi,redis,http,crypto,audit-postgres] @ git+ssh://git@github.com/prajwalmahajan101/resilience-kit.git@milestone/m7-rc1
```

Then `pip-compile requirements/base.in` to refresh `base.txt`.

**Django** — `requirements/base.in` (or `pyproject.toml` if uv-managed):

```text
resilience-kit[django,redis,http,crypto,audit-postgres] @ git+ssh://git@github.com/prajwalmahajan101/resilience-kit.git@milestone/m7-rc1
```

At M8 the pins flip to `resilience-kit==0.1.0` from PyPI. Per
[ROADMAP §Tagging convention](./ROADMAP.md#tagging-convention), `milestone/m7-rc1`
is a dev checkpoint and is NOT a PyPI release.

---

## 2. Deletion + import-rewrite table

One row per embedded path. The "Replace with" column is the public symbol your
remaining code should import.

### Both boilerplates

| Embedded path | Action | Replace with |
|---|---|---|
| `core/resilience/decorators.py` | delete | `from resilience_kit import resilient, circuit_breaker, retry, retry_on_failure` |
| `core/resilience/retry.py` | delete | `from resilience_kit import retry, retry_on_failure` |
| `core/resilience/registry.py` | delete | `from resilience_kit import registry` |
| `core/resilience/recovery.py` | delete | kit's `recovery.monitor` is launched by the adapter — no caller-side import |
| `core/resilience/circuit_breaker/` | delete | `from resilience_kit import circuit_breaker` (decorator) / `registry.get_breaker(name)` |
| `core/resilience/throttle(s)/` | delete | FastAPI: `from resilience_kit.adapters.fastapi import rate_limit` / Django: `from resilience_kit.adapters.django.drf_throttles import ...` |
| `core/resilience/cache/` | delete | `from resilience_kit.cache.provider import get_cache` |
| `core/resilience/health.py` | delete | `from resilience_kit import health_snapshot` |
| `core/api_log/` | delete | `from resilience_kit import log_inbound, log_outbound` / `from resilience_kit.audit import AuditEvent` |
| `core/api_log/sanitizers.py` | delete | `from resilience_kit.audit.sanitizers import Sanitizer` |
| `core/api_log/backends/` | delete | `from resilience_kit.audit.backends.{noop,stdlib_logging,postgres} import ...` |
| `core/utils/ssrf.py` *(FastAPI only)* | delete | `from resilience_kit.ssrf import resolve_and_validate, assert_allowed_url, assert_public_url` |
| `core/utils/crypto.py` | delete | `from resilience_kit import FernetCipher` |
| `core/utils/http_client/` | delete | `from resilience_kit import AsyncAPIClient` / `from resilience_kit.http_client import pinned_httpx_client, pinned_requests_session` |
| `core/utils/{log_sanitization,function_logger,network,timing,data}.py` | delete | `from resilience_kit.utils.{log_sanitization,function_logger,network,timing,data} import ...` |
| `core/utils/fire_and_forget.py` *(FastAPI only)* | delete | `from resilience_kit.dispatch.fire_and_forget import ...` |
| `core/middleware/request_id.py` | delete | (installed by adapter) |
| `core/middleware/body_limit.py` | delete | (installed by adapter) |
| `core/middleware/security_headers.py` | delete | (installed by adapter) |
| `core/middleware/selective_cors.py` | delete | (installed by adapter) |
| `core/middleware/rate_limit_headers.py` | delete | (installed by adapter) |
| `core/middleware/exception_logging.py` | delete | (installed by adapter) |
| `core/lifecycle/healthcheck.py` | delete | (mounted by adapter at `/readyz`) |
| `core/metrics.py` | delete | `from resilience_kit.metrics import MetricsSink` |
| `core/testing/reset.py` | delete | `from resilience_kit.testing.reset import reset_all_singletons` |
| `core/exceptions/` (infra/rate_limit/validation/repository) | gut → re-export | `from resilience_kit.exceptions import ExternalServiceError, RateLimitError, ValidationError, RepositoryError, ...` |

### FastAPI-only carve-outs

| Path | Action | Reason |
|---|---|---|
| `src/core/tasks/` | **KEEP** | Celery wrapper. The kit's `tasks/` is a lightweight in-process queue serving only the kit's audit dispatcher — not a Celery replacement. |
| `src/core/dispatch/` | n/a | Does not exist in fastapi_boilerplate. |
| `src/core/exceptions/handlers.py` | replace caller | The boilerplate-owned `register_exception_handlers` is replaced by `resilience_kit.adapters.fastapi.install_exception_handlers(app)`. Domain exception classes stay. |

### Django-only carve-outs

| Path | Action | Reason |
|---|---|---|
| `apps/core/middleware/{request_logging,throttling,metrics_middleware}.py` | **KEEP** | Boilerplate-specific; not in the kit's middleware set. |
| `apps/core/exceptions/{auth,api,handler,utils}.py` | **KEEP** | Boilerplate domain. Only `infrastructure.py`, `rate_limit.py`, `validation.py`, `repository.py` are gutted → re-export. |
| `apps/core/runtime.py` | delete | Kit's `resilience_kit.runtime.get_settings()` replaces it. |
| `apps/core/management/commands/resilience_{status,reset}.py` | delete | Kit's `resilience_kit.adapters.django` ships them. |
| `apps/core/base/fields.EncryptedCharField` | rewrite as re-export | `from resilience_kit.adapters.django.fields import EncryptedCharField` — existing model usages need no change. |
| `apps/core/resilience/throttles/drf_impl.py` | delete | DRF classes come from `resilience_kit.adapters.django.drf_throttles`. |

### Codemod commands

```bash
# FastAPI boilerplate
rg -l 'from src\.core\.resilience' src tests | xargs sed -i \
    -e 's|from src\.core\.resilience import|from resilience_kit import|g'
rg -l 'from src\.core\.api_log' src tests | xargs sed -i \
    -e 's|from src\.core\.api_log import|from resilience_kit.audit import|g'
rg -l 'from src\.core\.utils\.ssrf' src tests | xargs sed -i \
    -e 's|from src\.core\.utils\.ssrf|from resilience_kit.ssrf|g'
rg -l 'from src\.core\.utils\.crypto' src tests | xargs sed -i \
    -e 's|from src\.core\.utils\.crypto import FernetCipher|from resilience_kit import FernetCipher|g'
rg -l 'from src\.core\.utils\.http_client' src tests | xargs sed -i \
    -e 's|from src\.core\.utils\.http_client|from resilience_kit.http_client|g'

# Django boilerplate
rg -l 'from core\.resilience' apps tests | xargs sed -i \
    -e 's|from core\.resilience import|from resilience_kit import|g'
rg -l 'from core\.api_log' apps tests | xargs sed -i \
    -e 's|from core\.api_log import|from resilience_kit.audit import|g'
rg -l 'from core\.utils\.crypto' apps tests | xargs sed -i \
    -e 's|from core\.utils\.crypto import FernetCipher|from resilience_kit import FernetCipher|g'
rg -l 'from core\.utils\.http_client' apps tests | xargs sed -i \
    -e 's|from core\.utils\.http_client|from resilience_kit.http_client|g'
```

Commit per import-prefix for atomic history; eyeball the diff before each commit.

---

## 3. Settings translation

The kit's settings live in one `ResilienceSettings` model (env-prefixed `RESILIENCE_`,
nested delimiter `__`). See [LLD §10](./LLD.md#10-settings-schema) for the full schema.

### Env-var mapping

| Boilerplate setting | Kit env var | Notes |
|---|---|---|
| `CIRCUIT_BREAKER_CONFIG["backend"]` | `RESILIENCE_BACKEND` | `auto` / `memory` / `redis` / `pybreaker` |
| `CIRCUIT_BREAKER_CONFIG["redis_alias"]` / Valkey URL | `RESILIENCE_REDIS_URL` | `valkey://host:6379/0` works (same wire protocol). |
| `CIRCUIT_BREAKER_CONFIG["fail_max"]` | `RESILIENCE_DEFAULTS__CIRCUIT_BREAKER__FAIL_MAX` | default `5` |
| `CIRCUIT_BREAKER_CONFIG["reset_timeout"]` | `RESILIENCE_DEFAULTS__CIRCUIT_BREAKER__RESET_TIMEOUT` | seconds |
| `RETRY_CONFIG["max_attempts"]` | `RESILIENCE_DEFAULTS__RETRY__MAX_ATTEMPTS` | default `3` |
| `RATE_LIMIT_CONFIG["USER_RATES"]["auth"]` | `RESILIENCE_DEFAULTS__THROTTLE__AUTH_RATE` | `"5/min"` format |
| `OUTBOUND_ALLOWLIST` / `SSRF_ALLOWLIST` | `RESILIENCE_SSRF__OUTBOUND_ALLOWLIST` | JSON list `["partner.example", ".trusted.io"]` |
| `BLOCK_PRIVATE_IPS` | `RESILIENCE_SSRF__BLOCK_PRIVATE_IPS` | bool, default `true` |
| `FIELD_ENCRYPTION_KEY` | `RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY` | refuses prod-without-key (see [ADR 0008](./adr/0008-fernet-env-guard.md)) |
| `AUDIT_SINK` | `RESILIENCE_AUDIT__SINK` | `stdlib_logging` / `postgres` / importable string |
| `AUDIT_REDACT_FIELDS` | `RESILIENCE_AUDIT__REDACT_FIELDS` | JSON list |
| Metrics shim sink | `RESILIENCE_METRICS_SINK` | `noop` / `stdlib_logging` / importable string |

### Django: settings.RESILIENCE dict

Django's `DjangoSettingsSource` reads `settings.RESILIENCE` (mirroring the env shape).
Define it in `config/settings/base.py` and delete the legacy overlays:

```python
# config/settings/base.py — AFTER
RESILIENCE = {
    "backend": "redis",
    "redis_url": env("VALKEY_URL", default="valkey://localhost:6379/0"),
    "defaults": {
        "retry": {"max_attempts": 3, "wait_min": 1.0, "wait_max": 10.0},
        "circuit_breaker": {"fail_max": 5, "reset_timeout": 30.0},
        "throttle": {"auth_rate": "5/min"},
    },
    "ssrf": {"block_private_ips": True, "outbound_allowlist": ["*"]},
    "crypto": {"field_encryption_key": env("FIELD_ENCRYPTION_KEY", default=None)},
    "audit": {"sink": "postgres", "redact_fields": ["password", "token", "secret", "authorization"]},
}

# DELETE these legacy dicts — superseded by RESILIENCE:
#   CIRCUIT_BREAKER_CONFIG = {...}
#   RATE_LIMIT_CONFIG = {...}
#   FIELD_ENCRYPTION_KEY = "..."  (now under RESILIENCE["crypto"])
```

---

## 4. FastAPI lifespan diff

**Before** (`src/app.py`):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure(settings)
    await _fernet_probe()
    await wait_for_redis()
    await init_db_engine()
    await init_repository()
    recovery_monitor.start()
    try:
        yield
    finally:
        await recovery_monitor.stop()
        await drain_audit_logs()
        await close_http_clients()
        await dispose_db_engine()
```

**After:**

```python
from contextlib import asynccontextmanager
from resilience_kit.adapters.fastapi import (
    resilience_lifespan,
    install_exception_handlers,
    install_middleware_stack,
)

@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    # Boilerplate-owned setup (DB engine, domain repositories, ...)
    await init_db_engine()
    await init_repository()
    try:
        yield
    finally:
        await dispose_db_engine()

def create_app() -> FastAPI:
    app = FastAPI(lifespan=resilience_lifespan(inner=_app_lifespan))
    install_middleware_stack(app)
    install_exception_handlers(app)
    # ... boilerplate routers ...
    return app
```

`resilience_lifespan` mounts `/healthz` and `/readyz`, starts the recovery monitor and
audit dispatcher, and drains both on shutdown. Caller's `inner` lifespan wraps the
boilerplate's DB/repo setup inside.

---

## 5. Django `INSTALLED_APPS` / `MIDDLEWARE` / `REST_FRAMEWORK` diff

**Before** (`config/settings/base.py`):

```python
INSTALLED_APPS = [
    ...,
    "core",
    "core.api_log",
    ...,
]

MIDDLEWARE = [
    "core.middleware.selective_cors.SelectiveCORSMiddleware",
    "core.middleware.security_headers.SecurityHeadersMiddleware",
    "core.middleware.body_limit.ContentLengthLimitMiddleware",
    "core.middleware.request_id.RequestIDMiddleware",
    "core.middleware.exception_logging.ExceptionLoggingMiddleware",
    "core.middleware.request_logging.RequestLoggingMiddleware",       # boilerplate
    "core.middleware.rate_limit_headers.RateLimitHeadersMiddleware",
]

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "core.resilience.throttles.drf_impl.DRFUserTierThrottle",
        "core.resilience.throttles.drf_impl.DRFBurstThrottle",
    ],
    "EXCEPTION_HANDLER": "core.exceptions.handler.custom_exception_handler",
}
```

**After:**

```python
INSTALLED_APPS = [
    ...,
    "core",
    "resilience_kit.adapters.django",   # replaces "core.api_log"
    ...,
]

MIDDLEWARE = [
    "resilience_kit.adapters.django.middleware.SelectiveCorsMiddleware",
    "resilience_kit.adapters.django.middleware.SecurityHeadersMiddleware",
    "resilience_kit.adapters.django.middleware.BodyLimitMiddleware",
    "resilience_kit.adapters.django.middleware.RequestIdMiddleware",
    "resilience_kit.adapters.django.middleware.ExceptionLoggingMiddleware",
    "core.middleware.request_logging.RequestLoggingMiddleware",       # KEEP (boilerplate)
    "resilience_kit.adapters.django.middleware.RateLimitHeadersMiddleware",
]

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "resilience_kit.adapters.django.drf_throttles.UserTierThrottle",
        "resilience_kit.adapters.django.drf_throttles.BurstThrottle",
    ],
    "EXCEPTION_HANDLER": "resilience_kit.adapters.django.exception_handler.handle",
}
```

### `apps/core/apps.py`

Remove the recovery-monitor launch entirely — the kit's `ResilienceConfig.ready()`
(installed via `INSTALLED_APPS`) owns it now.

```python
# BEFORE
class CoreConfig(AppConfig):
    name = "core"

    def ready(self) -> None:
        self._start_recovery_monitor()
        ...

# AFTER
class CoreConfig(AppConfig):
    name = "core"

    def ready(self) -> None:
        # boilerplate-specific ready() work stays here
        ...
```

---

## 6. `EncryptedCharField` / `EncryptedString`

**Django** — `apps/core/base/fields.py` becomes a one-liner:

```python
from resilience_kit.adapters.django.fields import EncryptedCharField

__all__ = ["EncryptedCharField"]
```

The 2 model usages (`apps/accounts/models.py: APIKey.secret`) need no change. The
field's `deconstruct()` path changes, so run `./manage.py makemigrations --dry-run`
to confirm whether a no-op migration is needed (usually yes — generate it, commit it).

**FastAPI / SQLAlchemy** — replace the boilerplate's `EncryptedString` TypeDecorator
with `from resilience_kit.adapters.fastapi.fields import EncryptedString`.

---

## 7. Test-suite delta

### Conftest

```python
# tests/conftest.py — AFTER
import pytest
from resilience_kit.testing.reset import reset_all_singletons

@pytest.fixture(autouse=True)
async def _reset_resilience_singletons():
    await reset_all_singletons()
    yield
    await reset_all_singletons()
```

The kit also ships reusable pytest fixtures under `resilience_kit.testing.fixtures` —
import what you need rather than re-implementing.

### Tests to delete

Any test under `tests/unit/resilience/`, `tests/unit/api_log/`, `tests/unit/ssrf*`,
`tests/unit/crypto*`, `tests/unit/middleware/{request_id,body_limit,security_headers,
selective_cors,rate_limit_headers,exception_logging}_test.py` is testing kit-owned
code — delete. The kit's own contract suite covers them.

### Tests to keep but re-route

Integration tests that exercise the kit *through* the boilerplate's HTTP surface
(e.g. "a 429 is returned with `Retry-After`") stay — they're testing the wiring,
not the primitive. Update imports to reach kit symbols.

---

## 8. Verification checklist

Before opening the boilerplate PR:

- [ ] `pytest tests/unit -q && pytest tests/integration -q` green
- [ ] `pre-commit run --all-files` green
- [ ] App boots: FastAPI `uvicorn src.app:create_app --factory` / Django `./manage.py runserver`
- [ ] `/healthz` returns 200; `/readyz` returns 200 with all subsystems "ok"
- [ ] A throttled endpoint returns 429 with `Retry-After` header
- [ ] (Django) `./manage.py resilience_status` against a live Valkey container shows correct snapshot
- [ ] (Django) `./manage.py migrate --check` is clean OR a no-op migration for `EncryptedCharField` deconstruct path is committed
- [ ] (Django) `EncryptedCharField` round-trip via shell — `APIKey.objects.create(secret="x").secret == "x"`
- [ ] Kill Redis/Valkey container → `/readyz` flips to degraded → restart → recovers within ~5s
- [ ] Quote ROADMAP M7 "Exit when" line in the PR description and link to the green test output

---

## 9. Common gotchas

- **`httpx` version drift.** The kit pins `httpx>=0.27,<0.29` because the DNS-pinned
  resolver hook is fiddly across minor versions. If the boilerplate had `httpx>=0.28`,
  no change needed; if `<0.27`, bump it.
- **`redis-py` decode_responses.** Kit's Redis backends call `decode_responses=True`
  internally. If the boilerplate previously relied on raw bytes from a shared Redis
  client, route that code through the kit's cache provider or maintain a separate
  client for it.
- **Async-from-sync in Django.** Never call `await` paths from a sync Django view —
  go through the sync wrappers (`AsyncAPIClient.request_sync`, DRF throttle classes).
  See [docs/sync-vs-async.md](./sync-vs-async.md) and [ADR 0011](./adr/0011-django-sync-async-bridge.md).
- **Recovery monitor double-start.** Don't manually call `monitor.start()` — both
  adapters do it. If the boilerplate had a custom `atexit` registration for the
  monitor, delete it.
- **DRF throttle class names.** Kit uses `UserTierThrottle` (not `DRFUserTierThrottle`).
  Update `DEFAULT_THROTTLE_CLASSES` strings accordingly.

---

## 10. Patterns from the M7 dogfooding reports

The FastAPI and Django boilerplate migrations completed during the M7 cycle each surfaced patterns that aren't obvious from the deletion + import-rewrite table alone. Read this section *before* you start the migration — it covers four traps the dogfooders hit on the fly and the fixes that worked.

### 10.1 The exception bridge — make your base error a kit error

The simplest, highest-leverage change in both migrations was making the boilerplate's `BaseCustomError` (or equivalent) inherit from the kit's `ResilienceKitError`:

```python
# apps/core/exceptions/base.py — AFTER
from resilience_kit import ResilienceKitError

class BaseCustomError(ResilienceKitError):
    """Boilerplate's root exception — now also a ResilienceKitError."""
    ...
```

One line. Three downstream wins:

1. `@retry` and `@resilient` decorators (kit-side) can match on your `TransientError` / `ExternalTimeoutError` subclasses without you registering them anywhere.
2. The kit's exception handler can fall back to your envelope shape if your handler ever fails to load.
3. If you ship a kit-shaped microservice tomorrow, the same exception class works on both sides of the wire.

**Pin the invariant with a test.** The Django dogfooding report (§3.6) flagged this line as load-bearing and untested — if someone later removes it ("looks redundant?"), the kit handler will start catching domain exceptions and break your envelope. Add a one-line `assert issubclass(BaseCustomError, ResilienceKitError)` in your `tests/core/test_exceptions.py`.

### 10.2 Don't install two exception handler sets on the same app

This is the single most expensive footgun the FastAPI dogfooding hit (FastAPI report §0.2). Both kit and boilerplate ship exception handlers that target *different* base classes, so they don't shadow each other — but they emit *different* wire shapes:

| Raised by | Caught by | Wire shape |
|---|---|---|
| Code raising `BaseCustomError` subclasses | Boilerplate handler | `{success, message, data, errors:[{code, message, field, details}], request_id}` |
| Code raising `ResilienceKitError` subclasses (the kit's `RateLimitError`, `ValidationError`, `DecryptionError`, `ServiceUnavailableError`, etc.) | Kit handler | `{error_code, message, details}` |

If you `install_exception_handlers(app)` (kit) *and* `register_exception_handlers(app)` (boilerplate), rate-limited 429s and kit-infrastructure errors return the kit envelope; everything else returns yours. Existing API clients pattern-matching on `"success": false` break on rate-limited responses.

**Pick one shape and stick with it:**

- **Easiest** — apply the §10.1 exception bridge, then install **only** the boilerplate handler. The bridge makes `BaseCustomError` a `ResilienceKitError`, so subclassing each kit-shipped error into a boilerplate domain class (e.g. `class RateLimitError(BaseCustomError, ResilienceKitError.RateLimitError)`) lets your handler catch both trees with one envelope shape.
- **Loudest** — install **only** the kit handler and document the new envelope shape as the API contract going forward (breaking change for existing clients).
- **Most surgical** — install a small adapter handler that catches `ResilienceKitError`, re-wraps it as a `BaseCustomError`, and re-raises. Register it *before* both handler sets. ~15 LOC, no envelope-shape break for callers, no double-handler installation.

A `from_exception(exc, *, envelope_cls=None)` helper that does the third option is on the v0.1.x patch line (see [ROADMAP.md](./ROADMAP.md) "Beyond v0.1").

### 10.3 Wire your `request_id` ContextVar to the kit's

The kit ships its own `resilience_kit.context.request_id: ContextVar[str | None]`. Its `RequestIdMiddleware` writes to *that* variable, not yours. If the boilerplate had its own `request_id_ctx` ContextVar (every existing FastAPI / Django boilerplate does) and any of its code reads from `request_id_ctx` to render logs, audit rows, or envelope `request_id` fields, you have to either:

**Option A — rewrite consumers to read the kit's contextvar.** Cleanest. One import change in each consumer (`from src.core.context import request_id_ctx` → `from resilience_kit.context import request_id`). The kit's ContextVar becomes the single source of truth.

**Option B — bridge in a small middleware.** Install a middleware *after* the kit's `RequestIdMiddleware` that copies the kit's value into your contextvar. Lower diff churn, but you now have two contextvars carrying the same value with a one-frame copy window between them. Acceptable for short-term migrations.

This was finding §0.1 of the FastAPI dogfooding report — they shipped option B as a hot-fix to unblock the PR, then converted to option A in a follow-up. A `bind_to(consumer_ctxvar)` helper that makes option B a one-line subscription is on the v0.2 ROADMAP.

**Symptom you'll see if you skip this step:** every log line, audit row, response envelope, and exception you raise has `request_id: null`. It's silent — no error, no warning — so verify by hitting `GET /healthz` post-migration and checking the response/log JSON for a populated `request_id`.

### 10.4 Provider-API renames — old name → kit equivalent

The boilerplates' resilience layer had a slightly different surface than the kit's. The names that changed during the M7 migration:

| Pre-migration (boilerplate) | Post-migration (kit) | Notes |
|---|---|---|
| `backend.reset_backend(alias)` | `recovery.reset_provider(alias)` | Surgical reset of a single backend without touching the rest. `backend_name` attribute is no longer exposed on instances — read it from `HealthSnapshot.backend` instead. |
| `backend.backend_name` | `HealthSnapshot.backend` | Returned by `health_check()`; backend identity is now part of the snapshot, not the instance. |
| `backend.is_healthy()` | `(await backend.health_check()).healthy` | The kit returns a richer `HealthSnapshot(healthy, backend, degraded_since, detail, extra)` dataclass; pull `.healthy` if you only want the bool. |
| `cache.invalidate(key)` | `cache.delete(key)` | Method rename. |
| `breaker.force_close()` | `recovery.reset_provider(alias)` | Equivalent effect; the kit exposes the operation through recovery, not the breaker instance. |
| `throttle.GlobalThrottle` | *(not shipped in v0.1)* | The Valkey-Lua system-wide cap is on the v0.2 ROADMAP. Until then, fronting your service with an L7 reverse proxy (`nginx limit_req`) provides the same defence layer. |
| `AuthType` enum dispatch | `BasicAuth`, `BearerAuth`, `HMACAuth` classes | One-shot rename; a deprecation shim is on the v0.1.x patch line. |

`reset_all_singletons()` is now a sync function (was `async def` in the boilerplate); if your tests used `await reset_all_singletons()`, drop the `await` or call the upcoming `reset_all_singletons_async()` shim (v0.1.x patch line).

### 10.5 Operator env-var translation — required for every deployment

The boilerplate-shaped env-var names (`RATE_LIMIT_*`, `CIRCUIT_BREAKER_*`, `FIELD_ENCRYPTION_KEY`, `OUTBOUND_ALLOWLIST`, `THROTTLE_*`) are **not read** by the kit. A production deploy that pinned `RATE_LIMIT_ANON=200/hour` in its env file will silently fall back to the kit's default unless the env file is updated. This bit the Django dogfooding deploy (Django report §3.3) and would have bit the FastAPI deploy if the team hadn't read the env file first.

**Translation table** — copy this into your deployment runbook:

| Boilerplate env var | Kit env var |
|---|---|
| `FIELD_ENCRYPTION_KEY` | `RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY` |
| `RATE_LIMIT_ANON` | `RESILIENCE_DEFAULTS__THROTTLE__ANON_RATE` (or the per-scope key for your tier) |
| `RATE_LIMIT_AUTH` | `RESILIENCE_DEFAULTS__THROTTLE__AUTH_RATE` |
| `RATE_LIMIT_BURST` | `RESILIENCE_DEFAULTS__THROTTLE__BURST_RATE` |
| `CIRCUIT_BREAKER_FAIL_MAX` | `RESILIENCE_DEFAULTS__CIRCUIT_BREAKER__FAIL_MAX` |
| `CIRCUIT_BREAKER_RESET_TIMEOUT` | `RESILIENCE_DEFAULTS__CIRCUIT_BREAKER__RESET_TIMEOUT` |
| `OUTBOUND_ALLOWLIST` | `RESILIENCE_SSRF__OUTBOUND_ALLOWLIST` (JSON list, not a comma-separated string) |
| `REDIS_URL` | `RESILIENCE_REDIS_URL` |
| `RECOVERY_PROBE_INTERVAL` | `RESILIENCE_RECOVERY__PROBE_INTERVAL_SECONDS` |
| `AUDIT_SINK` | `RESILIENCE_AUDIT__SINK` |

Audit every env file (`.env`, `.env.staging`, `.env.production`, `helm/values-*.yaml`, `terraform/secrets.tf`, etc.) before promoting the migration branch past staging. A `legacy_env_alias()` translator that maps the old names with a one-time `DeprecationWarning` is on the v0.1.x patch line, but it requires a caller-side import — it does not auto-activate.

**Crypto-key fallback warning.** The kit's `FernetCipher` refuses to start in `environment="prod"` without `RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY`. The boilerplate's old fallback to `SECRET_KEY` is gone. Local / test environments still get the dev-key fallback; production deploys without the env var will fail at the first encrypt or decrypt call rather than silently using the wrong key.

---

## 11. After both PRs merge

1. Tag `milestone/m7` on the kit's `main` (dev checkpoint).
2. Proceed to M8: version bump, CHANGELOG, PyPI publish, GitHub release.
3. Open follow-up PRs to re-pin each boilerplate from `git+ssh://…@milestone/m7-rc1`
   to `resilience-kit==0.1.0`.
