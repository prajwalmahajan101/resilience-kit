# 0010 — FastAPI adapter shape

Status: accepted  ·  Date: 2026-06-10  ·  Milestone: M5

## Context

M0–M4 shipped a framework-agnostic kit: a `RecoveryMonitor` singleton,
an audit dispatcher, a `health_snapshot()` aggregator, six ASGI
middleware classes, a `ResilienceRegistry`, decorators (`@resilient`,
`@retry_on_failure`, `@circuit_breaker`), `AsyncAPIClient`, and
`FernetCipher`. M5 ships the FastAPI adapter that wires those
primitives into FastAPI's lifespan, dependency-injection, middleware,
and exception-handler hooks.

The adapter must be pure glue: ≲ 500 LOC, zero business logic,
copy-paste-friendly. If wiring it forces a primitive change in the
kit, that primitive is wrong — not the adapter.

## Decision

`resilience_kit.adapters.fastapi` exposes six public surfaces, each
covering a single FastAPI extension point:

1. **`resilience_lifespan(inner=None)`** — a factory returning a
   FastAPI lifespan that starts `recovery.monitor` on enter and, on
   exit, drains the audit dispatcher (5 s) before stopping the
   monitor. Accepts an optional inner lifespan so adopters chain their
   own startup hooks without giving up the kit's lifecycle. Factory
   rather than a bare context manager because FastAPI's
   `lifespan=` parameter accepts a callable taking the app — the
   factory closure captures `inner`.

2. **`install_health_routes(app, *, readyz_path, healthz_path,
   probe_timeout)`** — mounts `GET /healthz` (liveness) and
   `GET /readyz` (reads `health_snapshot`, propagates its
   `http_status`). Separated from `resilience_lifespan` because
   FastAPI only accepts a lifespan at `FastAPI(lifespan=...)`
   construction time, but routes can be added later.

3. **`install_exception_handlers(app)`** — registers handlers for
   `RateLimitError` (narrow, includes `Retry-After` +
   `X-RateLimit-*`) and `ResilienceKitError` (catch-all, status from
   `exceptions.http_status_for`). The handler reads the public
   `http_status_for` so the FastAPI handlers, the DRF handler (M6),
   and `ExceptionLoggingMiddleware` share a single LLD §11 table.

4. **`install_middleware_stack(app, **opts)`** — mounts the kit's six
   ASGI middleware in the recommended outer→inner order. Starlette
   wraps in reverse of the `add_middleware` call sequence; the source
   reads top→bottom from inside the stack out for trivial audit.
   `SelectiveCorsMiddleware` is skipped unless both `cors_allow_origins`
   and `cors_path_prefixes` are passed so apps that handle CORS
   upstream are never double-wrapped.

5. **`rate_limit(scope, rate, *, attr_from_request=None)`** — factory
   returning a FastAPI dependency that charges the kit's process-wide
   `AsyncThrottle` and raises `RateLimitError` on deny. The rate
   string is parsed *once* at dependency-build time. A built-in
   extractor handles `IP / ENDPOINT / GLOBAL / BURST / AUTH` from
   `request.client.host` and `request.url.path`; `USER_TIER`
   deliberately surfaces `ValidationError` unless the caller supplies
   an extractor — the kit has no opinion on authentication.

6. **`EncryptedString`** — SQLAlchemy 2.x `TypeDecorator[str]` over
   `FernetCipher`. `impl = String`, `cache_ok = True`. `None` passes
   through unchanged so nullable columns stay nullable.

### Things the adapter deliberately does *not* do

- **Wrap kit middleware.** Starlette accepts any ASGI3 callable via
  `app.add_middleware`; the kit's six classes already qualify. The
  adapter's `middleware.py` re-exports them and provides
  `install_middleware_stack` for the common ordering — it never
  subclasses or proxies.
- **Auto-install everything.** There is no single
  `setup_resilience(app)` god-helper. Adopters call the four `install_*`
  helpers in the order that suits their app. The cost is six import
  lines; the benefit is that exceptions / middleware / health routes
  can be wired independently and audited at PR review.
- **Hold its own settings.** Every knob comes from
  `runtime.get_settings()` or from `**opts` on the installer
  functions. The adapter never re-parses env or grows a settings
  schema.

### Sync mirror

FastAPI is async-only, so no sync wrapper ships. Adopters running a
sync handler that calls the kit go through `AsyncAPIClient.request_sync`
(M3) — refused inside a running loop by design.

### Extra gating

Every adapter module raises `MissingExtraError("fastapi", ...)` at
import if FastAPI / Starlette / SQLAlchemy is missing. The runtime
import sits inside a `try` block so the error fires at adapter import,
not deep inside a request.

## Consequences

- A reviewer can copy `tests/integration/fastapi_app/main.py` into a
  fresh project, `pip install prajwal-resilience-kit[fastapi,redis,crypto,audit-postgres]`,
  and have a working app under 100 LOC of glue.
- The LLD §11 exception → HTTP-status table now has one source
  (`exceptions.http_status_for`) shared by FastAPI, DRF (M6), and
  ASGI middleware. Future status changes are a single-file edit.
- `EncryptedString` couples the FastAPI extra to SQLAlchemy 2.x. Apps
  on SQLAlchemy 1.4 must pin `prajwal-resilience-kit` without the
  `[fastapi]` extra and hand-roll the field, or upgrade SQLAlchemy.
- `install_middleware_stack` opts into `SelectiveCorsMiddleware` only
  when both CORS arguments are present, so the default install is
  safe for apps that handle CORS upstream (Cloudflare, ingress).
- The recovery monitor's stop-event was rebound to handle test-harness
  loop reuse — see `fix(recovery): rebind monitor stop-event on every
  start`. That fix is pre-flight for both M5 and M6; it was not
  strictly an M5 deliverable but blocked the adapter's e2e suite.

## Usage

```python
from fastapi import Depends, FastAPI
from resilience_kit.adapters.fastapi import (
    EncryptedString,
    install_exception_handlers,
    install_health_routes,
    install_middleware_stack,
    rate_limit,
    resilience_lifespan,
)
from resilience_kit.throttle import Scope

app = FastAPI(lifespan=resilience_lifespan())
install_health_routes(app)
install_exception_handlers(app)
install_middleware_stack(app, cors_allow_origins=["*"], cors_path_prefixes=["/api"])

@app.get("/api/search", dependencies=[Depends(rate_limit(Scope.IP, "60/min"))])
async def search() -> dict[str, str]:
    return {"ok": "true"}
```

The SQLAlchemy column type is used identically to any other
`TypeDecorator`:

```python
from sqlalchemy.orm import Mapped, mapped_column
from resilience_kit.adapters.fastapi import EncryptedString

class Secret(Base):
    __tablename__ = "secrets"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(EncryptedString(512))
```
