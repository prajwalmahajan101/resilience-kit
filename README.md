# resilience-kit

> Framework-agnostic Python resilience + core-infrastructure kernel.
> Retries, circuit breakers, throttles, cache, SSRF guard, DNS-pinned HTTP client, audit decorators, field crypto — one package, pluggable backends, two thin adapters for Django and FastAPI.

[![PyPI](https://img.shields.io/pypi/v/resilience-kit.svg)](https://pypi.org/project/resilience-kit/)
[![Python](https://img.shields.io/pypi/pyversions/resilience-kit.svg)](https://pypi.org/project/resilience-kit/)
[![CI](https://github.com/prajwalmahajan101/resilience-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/prajwalmahajan101/resilience-kit/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> **Status:** v0.1 — pre-release. **M0–M3 merged** (scaffold · in-memory primitives · Redis/pybreaker backends · HTTP client + SSRF + crypto); latest dev checkpoint is [`milestone/m3`](https://github.com/prajwalmahajan101/resilience-kit/tree/milestone/m3). M4–M8 outstanding; no PyPI release yet — the first installable version will be `v0.1.0` (see [Tagging convention](./docs/ROADMAP.md#tagging-convention)). Design is locked across four docs:
>
> | Doc | What it answers |
> |---|---|
> | [PRD.md](./docs/PRD.md) | What's in/out of scope, why, who it's for |
> | [ROADMAP.md](./docs/ROADMAP.md) | Feature-level breakdown per milestone (M0–M8) with exit gates |
> | [LLD.md](./docs/LLD.md) | Protocols, sequence diagrams, concurrency model, settings schema |
> | [DIRECTORY-TREE.md](./docs/DIRECTORY-TREE.md) | Every file with arrival milestone and required extra |
>
> APIs marked *locked* in PRD §5.4 and LLD §2 will not break before 1.0.

---

## Why

`django_boilerplate` and `fastapi_boilerplate` were shipping the **same** resilience kernel against two web frameworks — retry, circuit breaker, Valkey-backed throttles, SSRF guard, DNS-pinned HTTP client, Fernet field crypto, `@log_inbound` / `@log_outbound` audit decorators — and it had already drifted. This package extracts the kernel **once**, makes every backend swappable, and ships thin adapters for both frameworks.

You probably want this if you've ever:

- Copy-pasted `retry` / `circuit_breaker` decorators between two services.
- Hand-rolled SSRF protection and then wondered if it survives DNS rebinding (it usually doesn't).
- Wrapped `redis-py` in a degrades-to-memory shim for the third time.
- Reached for `tenacity` and `pybreaker` and a custom Lua script and a sanitizer and a `ContextVar` request-id — all to add resilience to one outbound HTTP call.

---

## Install

```bash
pip install resilience-kit                        # core: pure-python, no I/O deps
pip install "resilience-kit[fastapi,redis,http]"  # FastAPI app on Valkey
pip install "resilience-kit[django,redis,http]"   # Django app on Valkey
pip install "resilience-kit[all]"                 # everything
```

### Available extras

| Extra | Enables |
|---|---|
| *(none)* | retry, in-memory breaker/throttle/cache, ssrf guard, audit decorators (noop sink), middleware factories, metrics shim, tasks queue, testing helpers |
| `[redis]` | Valkey / Redis backends for breaker, throttle, cache |
| `[pybreaker]` | `pybreaker` backend for the circuit breaker |
| `[http]` | DNS-pinned `AsyncAPIClient` (httpx) |
| `[requests]` | `pinned_requests_session()` |
| `[crypto]` | `FernetCipher` for field-level encryption |
| `[audit-postgres]` | Postgres audit-log backend |
| `[django]` | Django + DRF adapter |
| `[fastapi]` | FastAPI + Starlette adapter |
| `[all]` | everything above |
| `[dev]` | tooling: testcontainers, pytest-asyncio, mypy, ruff |

Importing a backend whose extra isn't installed raises `MissingExtraError("install resilience-kit[redis]")` at import time — no confusing `ModuleNotFoundError` deep in a stack trace.

---

## Quickstart — the one decorator you'll use the most

```python
from resilience_kit import resilient

@resilient("partner_api")          # circuit breaker (outer) + retry (inner)
async def get_balance(account_id: str) -> Decimal:
    response = await http_client.get(f"/accounts/{account_id}/balance")
    return Decimal(response.json()["balance"])
```

That's it. Defaults from settings: 3 retries with exponential backoff + jitter, breaker opens after 5 failures, half-opens after 30s. Per-service overrides:

```python
from resilience_kit import registry

registry.register_service("partner_api", {
    "retry":           {"max_attempts": 5, "wait_min": 2, "wait_max": 30},
    "circuit_breaker": {"fail_max": 3,     "reset_timeout": 60},
})
```

---

## FastAPI

```python
from fastapi import FastAPI, Depends
from resilience_kit.adapters.fastapi import lifespan, rate_limit, exception_handlers

app = FastAPI(lifespan=lifespan)
exception_handlers.install(app)

@app.get("/accounts/{id}", dependencies=[Depends(rate_limit("ip", "60/min"))])
async def read_account(id: str):
    ...
```

- `lifespan` starts the recovery monitor and mounts `/readyz`.
- `rate_limit(scope, rate)` is a FastAPI dependency over the kit's throttle.
- `exception_handlers.install(app)` maps kit exceptions (`ServiceUnavailableError`, `RateLimitError`, …) to JSON responses.

## Django

```python
# settings.py
INSTALLED_APPS = [..., "resilience_kit.adapters.django"]

MIDDLEWARE = [
    "resilience_kit.adapters.django.middleware.RequestIdMiddleware",
    "resilience_kit.adapters.django.middleware.RateLimitHeadersMiddleware",
    ...
]

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "resilience_kit.adapters.django.drf_throttles.IPThrottle",
        "resilience_kit.adapters.django.drf_throttles.UserTierThrottle",
    ],
    "EXCEPTION_HANDLER": "resilience_kit.adapters.django.exception_handler.handle",
}

RESILIENCE = {
    "BACKEND": "redis",
    "REDIS_URL": env("REDIS_URL"),
    "CRYPTO": {"FIELD_ENCRYPTION_KEY": env("FIELD_ENCRYPTION_KEY")},
}
```

`./manage.py resilience_status` shows per-service breaker state. `./manage.py resilience_reset partner_api` force-closes one.

---

## What's in the box

### Resilience primitives

| Primitive | Sync | Async | Backends |
|---|---|---|---|
| `@retry(...)` / `@retry_on_failure(name)` | ✅ | ✅ | n/a (pure logic) |
| `@circuit_breaker(name)` | ✅ | ✅ | `memory` (default), `pybreaker`, `redis` (atomic Lua) |
| `@resilient(name)` — breaker ∘ retry | ✅ | ✅ | — |
| Throttle — `rate_limit(scope, rate)` | ✅ | ✅ | `memory`, `redis` (global Lua) |
| Cache — `get_cache(alias)` | ✅ | ✅ | `memory` (TTL), `redis` |
| Recovery monitor — auto re-probe degraded backends | — | ✅ | — |

Scopes: `ip` · `endpoint` · `user_tier` · `global` · `burst` · `auth`. Rate syntax: `"60/min"`, `"10/sec"`, `"1000/hour"`.

### Security

```python
from resilience_kit.http_client import AsyncAPIClient
from resilience_kit.crypto import FernetCipher

async with AsyncAPIClient(service="partner_api") as client:
    # SSRF guard + DNS pin + outbound allow-list + breaker + retry + audit — all composed.
    data = await client.get("https://partner.example.com/v1/users/42")

token = FernetCipher.encrypt("very secret")
plaintext = FernetCipher.decrypt(token)
```

The DNS pin closes the classic validate→connect TOCTOU: the URL is validated *and* the resolved IPs are pinned into the same task-local `ContextVar` that the custom httpx resolver returns at dispatch time. A malicious zone that returns a public IP at validation and a private IP at request time gets blocked.

### Audit — `@log_inbound` / `@log_outbound`

```python
from resilience_kit.audit import log_outbound

@log_outbound(service="partner_api", redact=["card_number", "cvv"])
async def charge(card_number: str, cvv: str, amount: Decimal):
    ...
```

Pluggable sink: stdlib logging (default), Postgres (`[audit-postgres]`), Django ORM (via the Django adapter), or your own — see *Pluggability* below.

### Framework-agnostic middleware factories

`request_id`, `body_limit`, `security_headers`, `selective_cors`, `rate_limit_headers`, `exception_logging` — exposed as ASGI/WSGI factories. The Django and FastAPI adapters wrap them; you can also mount them directly in any Starlette / WSGI app.

---

## Pluggability

Every swappable subsystem is a `typing.Protocol` plus a provider that resolves implementations from (in order):

1. An explicit callable / instance you pass in.
2. A `RESILIENCE_<SUBSYSTEM>_BACKEND="myapp.module:MyBackend"` settings string.
3. An entry point named in your `pyproject.toml`.
4. A builtin (`memory`, `redis`, …).

Swappable subsystems at v0.1: **cache backend · circuit-breaker backend · throttle backend · audit sink · audit sanitizer · metrics sink · settings source · clock · audit dispatcher**.

### Shipping your own backend

```toml
# in your own package's pyproject.toml
[project.entry-points."resilience_kit.cache_backends"]
memcached = "rk_memcached:MemcachedCache"
```

```python
# rk_memcached.py
from resilience_kit.cache.base import AsyncCache

class MemcachedCache(AsyncCache):
    async def get(self, key): ...
    async def set(self, key, value, ttl=None): ...
    async def incr(self, key, amount=1): ...
    async def delete(self, key): ...
    async def health_check(self): ...
```

```bash
pip install rk-memcached
export RESILIENCE_CACHE_BACKEND=memcached
```

No fork. No monkey-patching. Same `@resilient` decorator everywhere.

---

## Configuration

Single `ResilienceSettings` model (pydantic v2). Resolved through `get_settings()` indirection so callers never import a global. Loaded from env with the `RESILIENCE_` prefix, or from `settings.RESILIENCE` in Django.

| Key | Default | Notes |
|---|---|---|
| `backend` | `auto` | `auto` / `redis` / `memory` / `pybreaker` |
| `redis_url` | `None` | when set, `[redis]` backends become available |
| `defaults.retry.max_attempts` | `3` | |
| `defaults.retry.wait_min` / `wait_max` | `1` / `10` | seconds |
| `defaults.circuit_breaker.fail_max` | `5` | |
| `defaults.circuit_breaker.reset_timeout` | `30` | seconds |
| `defaults.circuit_breaker.success_threshold` | `2` | half-open → closed |
| `defaults.throttle.auth_rate` | `5/min` | applied to `/auth/*` |
| `ssrf.block_private_ips` | `True` | |
| `ssrf.outbound_allowlist` | `["*"]` | exact host or `.suffix` |
| `crypto.field_encryption_key` | `None` | required outside dev/test |
| `audit.sink` | stdlib logging | importable string, callable, or entry-point name |
| `audit.redact_fields` | `["password", "token", "secret", "authorization"]` | |

Full pydantic schema in [LLD.md §10](./docs/LLD.md). Settings keys are loaded with the `RESILIENCE_` prefix and `__` nested delimiter (e.g. `RESILIENCE_DEFAULTS__RETRY__MAX_ATTEMPTS=5`).

---

## Exceptions you might catch

```python
from resilience_kit.exceptions import (
    TransientError,           # retryable, transport-layer
    ExternalTimeoutError,     # subtype of TransientError
    ExternalServiceError,     # upstream returned non-success
    ServiceUnavailableError,  # breaker is OPEN — adapter maps to 503
    RateLimitError,           # throttle tripped — adapter maps to 429
    DecryptionError,          # FernetCipher failed (key rotation?)
    ValidationError,          # SSRF guard / config-time validation
)
```

The Django and FastAPI adapters map these to the right HTTP responses out of the box.

---

## Testing your code that uses the kit

```python
from resilience_kit.testing import reset_all_singletons, FakeClock, FakeAuditSink

@pytest.fixture(autouse=True)
async def _reset():
    await reset_all_singletons()
```

Integration tests against real backends use `testcontainers-redis`:

```python
@pytest.mark.integration
async def test_throttle_under_load(redis_url):
    settings.RESILIENCE_REDIS_URL = redis_url
    # ... hammer the throttle, assert exact counts.
```

---

## Compatibility

- **Python**: 3.11, 3.12, 3.13
- **Django**: 4.2 LTS, 5.x
- **FastAPI**: 0.110+ (Starlette 0.36+)
- **httpx**: `>=0.27, <0.29`
- **Redis / Valkey**: Redis 7+, Valkey 8+ (verified in CI against both Docker images)

---

## Roadmap

**v0.1** — everything in this README, both adapters, both boilerplates migrated to depend on it. Nine milestones:

| | Milestone | Status |
|---|---|---|
| M0 | Repo scaffold | ⬜ pending |
| M1 | Core primitives, in-memory only | ⬜ pending |
| M2 | Redis/Valkey + pybreaker backends | ⬜ pending |
| M3 | HTTP client + SSRF + crypto | ⬜ pending |
| M4 | Audit + middleware + metrics + entry-point wiring | ⬜ pending |
| M5 | FastAPI adapter | ⬜ pending |
| M6 | Django adapter | ⬜ pending |
| M7 | Boilerplate migrations | ⬜ pending |
| M8 | v0.1.0 PyPI release | ⬜ pending |

**v0.2+** — Flask adapter · Celery adapter · Litestar adapter · `resilience_kit doctor` CLI · Sphinx site.

Per-milestone feature list and exit gates: [ROADMAP.md](./docs/ROADMAP.md). Final file tree with arrival milestones per file: [DIRECTORY-TREE.md](./docs/DIRECTORY-TREE.md).

---

## Contributing

This is a portfolio project — issues and PRs welcome but I'm the only maintainer. The contract test suite under `tests/contract/` is the source of truth: any new backend must pass it, parametrized in. See [LLD.md §12](./docs/LLD.md) for the test strategy and [DIRECTORY-TREE.md](./docs/DIRECTORY-TREE.md) for where new code lands.

```bash
uv sync --all-extras --dev
uv run pytest tests/contract -q              # contract suite, all backends
uv run pytest tests/integration -q           # adapter + testcontainers
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src
```

---

## License

MIT. See [LICENSE](./LICENSE).

---

## Related

- [`prajwalmahajan101/fastapi_boilerplate`](https://github.com/prajwalmahajan101/fastapi_boilerplate) — async FastAPI starter, will depend on this kit from its next release.
- [`prajwalmahajan101/django_boilerplate`](https://github.com/prajwalmahajan101/django_boilerplate) — Django 6 + DRF starter, ditto.
- Blog: *Circuit-breaker placement is different in async than sync — here's why.* (forthcoming on Hashnode)
