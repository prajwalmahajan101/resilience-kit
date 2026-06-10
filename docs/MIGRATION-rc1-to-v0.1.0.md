# Upgrading from `resilience-kit==0.1.0rc1` to `==0.1.0`

> **Audience:** any project pinned at `resilience-kit==0.1.0rc1` (the
> M7 boilerplate dogfood release). If you depended on `rc1` through a git
> ref or a `--pre` install on top of a less-specific pin, the same applies.
>
> **Time budget:** 5 minutes for a library user with no dogfood blockers
> (§1). 20–60 minutes for a boilerplate-style adopter who needs to apply
> the helper recipes in §3 to remove an open PR blocker.

---

## 1. Quick path — no dogfood blockers

If your project just *uses* the kit (import a few primitives, no custom
exception handler, no bespoke `request_id` ContextVar):

```diff
- resilience-kit==0.1.0rc1
+ resilience-kit==0.1.0
```

Re-run tests. Done. The public import surface, settings keys, and wire
shapes of every adapter are unchanged from `rc1`. Skip to §5 to file a
two-line "no issues" migration report.

If your project hit any of the M7 dogfooding findings (FastAPI #B1 /
#B2, Django D-Env, Django §3.6 untested-bridge), continue to §2.

---

## 2. What shipped in v0.1.0

Five additive helpers landed in PR #22 specifically to close the M7
dogfooding findings. None of them break existing surface; you opt in by
importing.

| Helper | Import | Closes |
|---|---|---|
| `bind_to(target)` | `from resilience_kit.context import bind_to` | FastAPI #B1 — `request_id` was `null` in the boilerplate's own context layer because the kit's middleware only writes to its own ContextVar. |
| `reset_all_singletons_async()` | `from resilience_kit.testing import reset_all_singletons_async` | Sync/async drift — async test harnesses no longer need `asyncio.to_thread`. |
| `verify_envelope_contract(handler, envelope_schema, exceptions=...)` | `from resilience_kit.testing import verify_envelope_contract` | Django §3.6 untested-bridge — pins an adopter's `BaseCustomError(ResilienceKitError)` invariant across refactors. |
| `from_exception(exc, *, envelope_cls=None, extra_headers=None)` | `from resilience_kit.adapters._envelope import from_exception` | FastAPI #B2 — two exception envelopes on the same app; lets an adopter re-wrap kit exceptions into their existing envelope shape with one call. |
| `legacy_env_alias(env=None, aliases=DEFAULT_ALIASES, warn=True)` | `from resilience_kit.runtime import legacy_env_alias` | Django D-Env — legacy env-var names (`RATE_LIMIT_*`, `CIRCUIT_BREAKER_*`, `FIELD_ENCRYPTION_KEY`, …) silently dropped tuning on the next deploy. |

`rc1` already shipped the **breaking** `ResilienceSettings(extra="forbid")`
change (PR #15, ISSUE-002) — `0.1.0` does **not** add a second breaking
change. If `rc1` worked, `0.1.0` works.

For *why* each helper exists and the underlying mechanics, see
[`MIGRATION-from-boilerplate-embedded.md` §10](./MIGRATION-from-boilerplate-embedded.md#10-patterns-from-the-m7-dogfooding-reports).
This doc is the *how*, not the *why*.

---

## 3. Blocker → helper recipes

Each subsection is self-contained: minimal before, minimal after, one
sentence on the mechanism. Apply only the recipes that match a blocker
your PR is carrying.

### 3.1 B1 — `request_id` is `null` everywhere

**Symptom.** Every log line, response envelope, audit row, and exception
field carries `"request_id": null`. The kit's
`RequestIdMiddleware` set a value on `resilience_kit.context.request_id`,
but your code reads from your own `request_id_ctx` ContextVar (a holdover
from the boilerplate's pre-kit context layer) and nobody is writing to it.

**Fix.** Wrap your request-id middleware body in
`bind_to(your_ctxvar)` so the kit value mirrors into your ContextVar for
the lifetime of the request.

```python
# src/core/middleware.py (or apps/core/middleware.py for Django)
from resilience_kit.context import bind_to
from src.core.context import request_id_ctx          # your own ContextVar

class YourRequestIdMiddleware:
    async def __call__(self, scope, receive, send):
        # Whatever you do to seed kit's request_id first — typically the
        # kit's own RequestIdMiddleware runs upstream and has already done it.
        with bind_to(request_id_ctx):
            await self.app(scope, receive, send)
```

Django sync middleware is the same shape — a `with bind_to(...)` block
inside `__call__` / `process_request`.

**Verify.** `curl -i localhost:8000/healthz` should return a JSON body
whose `request_id` field is a 32-char hex string, not `null`. Log lines
emitted during that request should carry the same id.

### 3.2 B2 — Two exception envelopes on the same app

**Symptom.** Your app installs **both** the kit's
`install_exception_handlers(app)` and your project's existing
`register_exception_handlers(app)`. Kit-raised errors (`RateLimitError`,
`DecryptionError`, `ServiceUnavailableError`) return
`{error_code, message, details}`; project-raised errors return
`{success, message, data, errors, request_id}`. Clients pattern-matching
on `"success": false` break on 429s and on every kit-infra 5xx.

**Fix.** Install **only your project's handler**, but route every
`ResilienceKitError` through `from_exception(exc, envelope_cls=YourEnvelope)`
inside it so the kit exception's body comes back already projected onto
your envelope's field names.

```python
# src/core/exception_handlers.py
from resilience_kit.adapters._envelope import from_exception
from resilience_kit.exceptions import ResilienceKitError
from src.core.envelope import ResponseEnvelope   # your pydantic model

async def on_kit_error(request, exc: ResilienceKitError):
    body, status, headers = from_exception(exc, envelope_cls=ResponseEnvelope)
    return JSONResponse(body, status_code=status, headers=headers)

def register_exception_handlers(app):
    app.exception_handler(ResilienceKitError)(on_kit_error)
    # ... your existing project-domain handlers
```

The projection looks at `ResponseEnvelope.model_fields` and writes onto
whichever aliases you declared:

| Canonical | Envelope field names it will fill (first match wins) |
|---|---|
| `error_code` | `error_code` / `code` / `error` |
| `message` | `message` / `detail` |
| `details` | `details` (dict) **or** `errors` (DRF-style list of `{field, message}`) |
| `request_id` | `request_id` (filled from `resilience_kit.context.request_id.get()`) |
| `success` | `success` (always `False` for an error envelope) |

**Do not** also call `install_exception_handlers(app)` from the kit's
FastAPI adapter — that's the double-install that produced the two-envelope
bug. Same advice for Django: do **not** set
`REST_FRAMEWORK['EXCEPTION_HANDLER']` to the kit's `handle`; use your own
DRF handler and route through `from_exception` inside it.

**Verify.** Hit a rate-limited endpoint 3× and confirm the 429 body
matches your envelope schema (`success: false`, `errors: [...]`,
`request_id: <hex>`), and that `Retry-After` + `X-RateLimit-*` headers
are present.

### 3.3 D-Env — Legacy env-vars silently drop tuning on deploy

**Symptom.** Your `.env.production` pins names like `RATE_LIMIT_AUTH`,
`CIRCUIT_BREAKER_FAIL_MAX`, or `FIELD_ENCRYPTION_KEY` — names the
pre-kit boilerplate used. The kit only reads `RESILIENCE_*`. On the next
deploy you silently lose every tuning value and fall back to the kit's
defaults. The kit emits no warning.

**Fix.** Call `legacy_env_alias()` once at the top of your settings
module, **before** `ResilienceSettings()` is instantiated.

```python
# settings/base.py (Django) or src/core/settings.py (FastAPI)
from resilience_kit.runtime import legacy_env_alias

legacy_env_alias()        # translates legacy → RESILIENCE_* in os.environ,
                          # emits a DeprecationWarning per alias used.

# ... your normal settings import follows.
```

The kit-prefixed name always wins on collision. The `DeprecationWarning`
gives operators a deterministic signal to fix `.env*` files in their own
time. Pass `warn=False` to silence it in short-lived CI jobs; pass a
narrower `aliases=` dict to bridge only a subset.

**Verify.** Set a legacy var (`RATE_LIMIT_AUTH=30/min`) in a throwaway
shell, import your settings module, and confirm:
1. `os.environ['RESILIENCE_DEFAULTS__THROTTLE__AUTH_RATE'] == '30/min'`.
2. A `DeprecationWarning` mentioning `RATE_LIMIT_AUTH` fired during import.

### 3.4 Django §3.6 — Untested exception-bridge invariant

**Symptom.** Your handler bridges kit exceptions into your envelope
(either via `from_exception` from §3.2 or by subclassing each kit
exception). Today no test asserts the bridge stays valid for every kit
exception class — only for the one or two you happened to write a test
for. A future kit release that adds a class, or a refactor of your
handler, can silently regress one branch.

**Fix.** Add one test that exercises every HTTP-reachable kit exception
through your handler + envelope schema.

```python
# tests/test_envelope_contract.py
from resilience_kit.testing import verify_envelope_contract
from src.core.exception_handlers import on_kit_error
from src.core.envelope import ResponseEnvelope

def test_kit_envelope_contract():
    verify_envelope_contract(
        handler=lambda exc: on_kit_error(request=None, exc=exc).body,
        envelope_schema=ResponseEnvelope.model_validate,
    )
```

If any kit exception's projected body doesn't validate against
`ResponseEnvelope`, the test fails with an `AssertionError` that lists
**every** broken class — not just the first one — so the failure report
is actionable in one CI run.

**Verify.** Deliberately break your handler (e.g. drop the `errors`
field) and confirm the test fails listing every exception class.

### 3.5 Async test ergonomics

**Symptom.** Your async fixtures wrap `reset_all_singletons()` in
`asyncio.to_thread`. The underlying reset is non-blocking — the
`to_thread` was pure ergonomic friction.

**Fix.**

```diff
- import asyncio
- await asyncio.to_thread(reset_all_singletons)
+ from resilience_kit.testing import reset_all_singletons_async
+ await reset_all_singletons_async()
```

No mechanism change — the wrapper just calls the sync function.

---

## 4. Adopter checklist

Linear, top-to-bottom. Each step should pass before moving to the next.

- [ ] **Step 1 — Pin bump.** Change `resilience-kit==0.1.0rc1` → `resilience-kit==0.1.0` in `requirements.txt` / `pyproject.toml`. Drop any `--pre` install flags in CI scripts.
- [ ] **Step 2 — Helpers.** Apply only the §3 recipes that match the blockers your PR carries. Do **not** apply recipes proactively — every import is opt-in and you should leave dormant ones for a separate PR with its own justification.
- [ ] **Step 3 — Unit suite.** Your repo's full unit test suite passes against the new pin. Pay attention to any test that previously asserted `request_id is None` — it should now assert a real id (or be removed).
- [ ] **Step 4 — Integration / contract suite.** Whatever suite hits a real Redis / Postgres / Valkey passes against `==0.1.0`. The kit's own integration suite did not change in `0.1.0` relative to `rc1`, so adopter-side failures here are almost always wiring drift, not a kit regression.
- [ ] **Step 5 — Runserver smoke (5 min).** Start your app locally and hit, in order:
  - `GET /healthz` — expect 200 + a body with a 32-char hex `request_id`.
  - `GET /readyz` — expect 200 (or 503 if a backend probe legitimately fails).
  - one authenticated endpoint — request_id non-null in both the response body and the log line.
  - one rate-limited endpoint, hit it past the limit — expect 429 with `Retry-After` header + your envelope's `errors`/`details` populated.
- [ ] **Step 6 — Migration report.** Fill in the §5 template and file it. This is the gate that makes future kit releases better; please do not skip it.

---

## 5. Migration report template

Copy the fenced block below into a new file in your repo at
`docs/m8b-upgrade-report.md` (or wherever your project files release
notes). Fill in every section honestly — "no issues" answers are useful
signal, not failure.

When the report is ready, either:
- comment a link to the file in `resilience-kit`'s GitHub issue tracker,
  **or**
- open a tiny PR against `resilience-kit` adding a copy at
  `docs/m8b-upgrade-reports/<your-repo>.md`.

Either intake is fine — the kit will collate both for v0.1.x / v0.2
ROADMAP planning.

````markdown
# resilience-kit `0.1.0rc1` → `0.1.0` migration report

- **Project:** `<repo name>`
- **Date:** `<YYYY-MM-DD>`
- **Pin moved:** `==0.1.0rc1` → `==0.1.0`
- **Branch / PR:** `<link>`

## Outcome score (1-10)

Score: `_/10`. One sentence on why: ...

## Blockers hit and resolved

- [ ] B1 — `request_id` null in our context layer.
  - Resolved by: `bind_to(target)` / our own fix / not applicable
- [ ] B2 — two exception envelopes on the same app.
  - Resolved by: `from_exception(envelope_cls=...)` / our own fix / not applicable
- [ ] D-Env — legacy env-var names silently dropped tuning.
  - Resolved by: `legacy_env_alias()` / runbook audit / not applicable
- [ ] Django §3.6 — untested exception-bridge invariant.
  - Resolved by: `verify_envelope_contract(...)` / our own test / not applicable
- [ ] Other (describe): ...

## Helpers used

- [ ] `resilience_kit.context.bind_to`
- [ ] `resilience_kit.adapters._envelope.from_exception`
- [ ] `resilience_kit.runtime.legacy_env_alias`
- [ ] `resilience_kit.testing.verify_envelope_contract`
- [ ] `resilience_kit.testing.reset_all_singletons_async`

## Missing surface (kit wishlist)

Things the kit didn't expose that you ended up wishing it did. One bullet
per gap; brief is fine.

- ...
- ...

## Time spent per phase

| Phase | Hours | Notes |
|---|---|---|
| Reading docs | | |
| Applying helper recipes | | |
| Test suite green | | |
| Runserver smoke | | |
| Writing this report | | |
| **Total** | | |

## Doc gaps

What `MIGRATION-rc1-to-v0.1.0.md` (this doc) or
`MIGRATION-from-boilerplate-embedded.md` did not cover, or covered
misleadingly:

- ...

## Pain points

Anything subjective worth flagging — surprise behaviour, opaque error
messages, hard-to-find imports, missing types, etc.

- ...

## Suggested ROADMAP additions

Things you'd like to see ship in v0.1.x / v0.2 / later. Be specific:
"add `X` so I can stop writing `Y`".

- ...
````

---

## Appendix A — FastAPI boilerplate step list

Concrete files in `fastapi_boilerplate` to touch (adjust paths to match
your fork). Each line names the file and the single import/call to add.

| File | Change |
|---|---|
| `pyproject.toml` or `requirements.txt` | `resilience-kit==0.1.0rc1` → `resilience-kit==0.1.0`. |
| `src/core/middleware.py` (request-id middleware) | Add `from resilience_kit.context import bind_to`. Wrap the body in `with bind_to(request_id_ctx):`. (§3.1.) |
| `src/core/exception_handlers.py` | Add `from resilience_kit.adapters._envelope import from_exception`. Replace the kit-exception handler body with the §3.2 snippet. **Remove** any call to `install_exception_handlers(app)` from `resilience_kit.adapters.fastapi.exception_handlers`. |
| `src/core/settings.py` | Add `from resilience_kit.runtime import legacy_env_alias` and call it at module top. (§3.3.) |
| `tests/conftest.py` | Add `from resilience_kit.testing import reset_all_singletons_async`. Replace any `asyncio.to_thread(reset_all_singletons)` with `await reset_all_singletons_async()`. |
| `tests/test_envelope_contract.py` (new file) | Paste the §3.4 snippet pointed at your `ResponseEnvelope`. |

Then run §4 steps 3–6.

---

## Appendix B — Django boilerplate step list

| File | Change |
|---|---|
| `pyproject.toml` | `resilience-kit==0.1.0rc1` → `resilience-kit==0.1.0`. |
| `settings/base.py` | Add `from resilience_kit.runtime import legacy_env_alias` and call it at module top, **before** `from resilience_kit.settings import ResilienceSettings` / before any pydantic-settings instance is constructed. (§3.3.) |
| `apps/<core>/middleware.py` (request-id middleware) | Add `from resilience_kit.context import bind_to`. Wrap `__call__` body in `with bind_to(request_id_ctx):`. (§3.1.) |
| `apps/<core>/exception_handlers.py` | Add `from resilience_kit.adapters._envelope import from_exception`. Use the §3.2 snippet inside a DRF-shaped handler. **Do not** set `REST_FRAMEWORK['EXCEPTION_HANDLER']` to `resilience_kit.adapters.django.exception_handler.handle` — keep your own DRF handler and route through `from_exception`. |
| `tests/conftest.py` | Same `reset_all_singletons_async` swap as Appendix A. |
| `tests/test_envelope_contract.py` (new file) | Same §3.4 snippet, pointed at your DRF envelope serializer / pydantic schema. |

Then run §4 steps 3–6.

---

## Appendix C — What's NOT closed in v0.1.0

These are deliberately out of scope; do not expect this migration alone
to address them.

- **`RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY` must be set in production.**
  `FernetCipher` refuses to start in `environment="prod"` without it.
  There is no fallback to `SECRET_KEY` or any other Django/FastAPI
  setting. `legacy_env_alias()` translates `FIELD_ENCRYPTION_KEY` →
  `RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY` if the legacy name is set,
  but if **neither** is set the kit fails fast — that is the intended
  behaviour (see [ADR 0008](./adr/0008-fernet-env-guard.md)).
- **Env-file audit is still recommended.** `legacy_env_alias()` is opt-in
  and only translates names listed in `DEFAULT_ALIASES`. If your team
  added project-specific environment names that diverge from the
  boilerplate table, those still need a hand-audit. See
  [`MIGRATION-from-boilerplate-embedded.md` §10.5](./MIGRATION-from-boilerplate-embedded.md#105-operator-env-var-translation--required-for-every-deployment).
- **`GlobalThrottle`, `AsyncFernetCipher`, real `DjangoSettingsSource`,
  Flask / Celery / Litestar adapters, `resilience_kit doctor` CLI.**
  All deferred to v0.2 / v0.3. See
  [`ROADMAP.md`](./ROADMAP.md) for the canonical post-v0.1 list and
  [`RELEASE-PLAN.md`](./RELEASE-PLAN.md) §6 / §7 for the task
  breakdowns.

If something an adopter needs is not on either list, file it as a kit
wishlist item in the §5 migration report — that is the intake path for
v0.1.x / v0.2 scope.
