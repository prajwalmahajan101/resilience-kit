# Known Issues — `resilience-kit` v0.1.0

> Catalog of every issue surfaced by the four-lens audit (`audit/RKIT-L{1,2,3,4}-*.md`) plus the synthesised next-steps + ratings files. **35 issues** total, grouped by lane and ordered by Impact ÷ Effort priority.
>
> **Status legend:** `open` · `in-progress` · `fixed` (link the PR/tag that fixed it) · `wontfix` (with rationale) · `deferred` (with target milestone)
>
> **GH column:** GitHub issue number when filed. Empty = not yet on the tracker.
>
> Update protocol: any PR that changes status here must touch this file in the same commit. Don't rely on memory.

---

## Severity legend

| Tag | Meaning |
|---|---|
| 🔴 **CRITICAL** | Active security or correctness vulnerability with realistic exploit path. Block adoption until fixed. |
| 🟠 **HIGH** | Correctness bug, locked-API drift, or reliability gap that bites under production load. Ship in v0.1.1. |
| 🟡 **MEDIUM** | Hygiene, code-quality, or doc-fidelity gap. Ship in v0.1.x. |
| 🟢 **LOW** | Quick wins, OSS hygiene, classifier corrections. Ship in next patch. |
| 🔵 **ECOSYSTEM** | New surfaces (Flask/Celery adapters, CLI, docs site). Deferred to v0.2/v0.3. |

---

## Index

- [Lane A — Sub-day wins (10 issues)](#lane-a--sub-day-wins)
- [Lane B — v0.1.1 patch (8 issues)](#lane-b--v011-patch)
- [Lane C — v0.2.0 minor (6 issues)](#lane-c--v020-minor)
- [Lane D — v0.3.0+ maturity (11 issues)](#lane-d--v030-maturity)

---

## Lane A — Sub-day wins

Each fits in <1 day. Total effort ~6 hours. Closes 10 issues, lifts OSS-readiness 6.5 → 8.0.

### #A1 🟢 Add `Cookie`, `Set-Cookie` to default audit redaction set

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 1 · **Priority:** 3.00 · **GH:** _unfiled_ · **Status:** `fixed` (branch `fix/lane-a-quickwins`)

**Where:** `src/resilience_kit/audit/sanitizers.py:52-59` (`DEFAULT_FIELDS`)

**Problem.** `DEFAULT_FIELDS = ("password", "token", "secret", "authorization", "api_key", "x-api-key")` — missing `cookie` and `set-cookie`. If a caller logs request/response headers via a `payload_factory`, session cookies leak to audit logs and any downstream sink.

**Why this matters.** Session cookies are auth-bearing. CWE-532 (cleartext storage in log). Most fintech / compliance auditors block on this.

**Fix.** Append `"cookie", "set-cookie"` to `DEFAULT_FIELDS`. Add a test in `tests/unit/audit/test_sanitizers.py` asserting both names are redacted (and `set-cookie` is matched case-insensitively).

**Acceptance.** A `payload_factory` returning `{"headers": {"Cookie": "session=abc123"}}` produces a sanitised event whose `payload.headers.Cookie == "[REDACTED]"`.

---

### #A2 🟡 Remove dead `__acall__` methods from Django middleware

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 1 · **Priority:** 3.00 · **GH:** _unfiled_ · **Status:** `fixed` via option (a) (branch `fix/lane-a-quickwins`) — 6 `__acall__` deleted, docstring corrected, dispatch-shape guard test added; native async deferred to #C6/#D2

**Where:** `src/resilience_kit/adapters/django/middleware.py:105, 150, 190, 240, 282, 322`

**Problem.** Every Django middleware in the kit defines `async def __acall__(self, request)`. Django's async-middleware contract does **NOT** dispatch via `__acall__` — Django looks for a `__call__` returning an awaitable (with `markcoroutinefunction` or `_is_coroutine` marker), or uses `MiddlewareMixin` autodetection. Under ASGI Django, the framework sees both sync_capable + async_capable, picks `__call__` (sync), and wraps via `sync_to_async`.

Result: `__acall__` is unreachable code. Six occurrences across the file.

**Why this matters.** Contradicts ADR-0011's "both sync and async modes are supported." Shipping unreachable code in a *locked* adapter surface is a credibility issue.

**Fix.** Either (a) delete `__acall__` and document that ASGI Django uses sync→async wrapping, or (b) implement the documented Django async-middleware recipe (`__call__` returning awaitable + `sync_and_async_capable` marker). Option (a) is the faster path; option (b) is the right path if performance under ASGI matters.

**Acceptance.** No `__acall__` definitions remain (option a) OR an ASGI integration test asserts the async path is exercised (option b).

---

### #A3 🟡 Reconcile ADR-0009 vs ADR-0004 vs `_providers.py`

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 1 · **Priority:** 3.00 · **GH:** _unfiled_ · **Status:** `fixed` (branch `fix/lane-a-quickwins`). Root cause was narrower than written: ADR-0009's numbered chain, ADR-0004, and `_providers.py` all already agree (EPs shadow builtins); only two ADR-0009 prose paragraphs claimed the reverse, and `test_builtin_resolves_first` carried the same false claim (it never installed a colliding EP). Fixed: amended ADR-0009 prose to match the code, renamed/clarified the misleading test, and added `test_entry_point_shadows_same_named_builtin` that installs a `fake` EP colliding with a `fake` builtin and proves the EP wins.

**Where:**
- `docs/adr/0004-entry-points-for-third-party-backends.md`
- `docs/adr/0009-entry-point-precedence-chain.md`
- `src/resilience_kit/_providers.py:91-98`

**Problem.** Three sources disagree about backend resolution order:

| Source | Claims |
|---|---|
| ADR-0004 | Entry points **shadow** builtins (intentional, for third-party override) |
| ADR-0009 | Builtins **shadow** entry points (kit-shipped names are reserved) |
| `_providers.py:91-98` | Iterates entry points **first** and returns first match — matches ADR-0004 |

**Why this matters.** An operator reading ADR-0009 will reason incorrectly about which backend wins. This is the worst architecture-trust bug in the repo.

**Fix.** Pick the policy that matches the code (ADR-0004's "EPs shadow builtins"). Mark ADR-0009 as `Superseded by ADR-0004`. Update CHANGELOG. If the policy *should* be the opposite, fix the code in `_providers.py` and write a new ADR — but the code-as-shipped is the default-correct interpretation.

**Acceptance.** Exactly one ADR documents the resolution policy. The other is marked Superseded with a date. Code matches the surviving ADR.

---

### #A4 🟢 Bump `Development Status :: 3 - Alpha` → `4 - Beta`

**Severity:** LOW · **Impact:** 2 · **Effort:** 1 · **Priority:** 2.00 · **GH:** _unfiled_ · **Status:** `fixed` (branch `fix/lane-a-quickwins`) — classifier bumped + CHANGELOG `### Changed`

**Where:** `pyproject.toml` `[project]` classifiers

**Problem.** Classifier `Development Status :: 3 - Alpha` on a library that survived an rc1 → v0.1.0 cycle with a 556-line migration guide, two adopter dogfood reports, locked API surface, and Trusted Publishing. Adopters scan classifiers to gate prod adoption; "Alpha" reads as "not ready" and undersells the work.

**Fix.** Change to `Development Status :: 4 - Beta` in `pyproject.toml`. Note in CHANGELOG under `### Changed`.

**Acceptance.** `pip show resilience-kit` displays "Beta". Procurement checklists that filter `>= Beta` no longer skip this package.

---

### #A5 🟢 Configure dependabot `automerge` on patch/minor when CI green

**Severity:** LOW · **Impact:** 2 · **Effort:** 1 · **Priority:** 2.00 · **GH:** _unfiled_ · **Status:** `fixed` (branch `fix/lane-a-quickwins`) — added `.github/workflows/dependabot-automerge.yml` (patch/minor via `fetch-metadata@v2` + `gh pr merge --auto`; majors manual)

**Where:** `.github/dependabot.yml`; possibly a new workflow `.github/workflows/dependabot-automerge.yml`

**Problem.** Dependabot PRs (#26, #27 currently, plus three new branches as of 2026-06-24: `checkout-7`, `download-artifact-8`, `upload-artifact-7`) queue without an SLA. The library trusts dependabot to *open* PRs but not to *merge* them — incoherent.

**Fix.** Add `dependabot-automerge.yml` workflow that enables auto-merge on patch + minor updates when all required checks pass. Keep major updates manual. Pin to `dependabot/fetch-metadata@v2` for safety.

**Acceptance.** A patch-level dependabot PR opens, CI goes green, PR auto-merges within 5 minutes with no human intervention.

---

### #A6 🟢 Add `CODE_OF_CONDUCT.md` (Contributor Covenant)

**Severity:** LOW · **Impact:** 1 · **Effort:** 1 · **Priority:** 1.00 · **GH:** _unfiled_ · **Status:** `fixed` (branch `fix/lane-a-quickwins`) — Contributor Covenant v2.1 added; linked from README + CONTRIBUTING; enforcement contact via GitHub Security Advisories / maintainer

**Where:** Repo root

**Problem.** Most corporate procurement checklists require a Code of Conduct. The kit ships SECURITY, CONTRIBUTING, but not CoC. Required for the OpenSSF Best Practices badge.

**Fix.** Drop in Contributor Covenant v2.1 verbatim (~30 lines). Reference from CONTRIBUTING.md and README.

**Acceptance.** `CODE_OF_CONDUCT.md` present, linked from README community section.

---

### #A7 🟢 Add `--cov-fail-under` gate to CI

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 1 · **Priority:** 3.00 · **GH:** _unfiled_ · **Status:** `fixed` (branch `fix/lane-a-quickwins`). Added `--cov-fail-under` to the CI `test` job. Floor set to **68** (not 85): the gated `test` job runs without Redis/integration, so the Redis backends are uncovered there (~69% measured) — those paths are covered in `integration.yml`. Follow-up: fold a Redis-backed coverage job in and raise the floor toward 85.

**Where:** `.github/workflows/ci.yml` test job; `pyproject.toml` already has `[tool.coverage]`

**Problem.** `pytest-cov` is declared in `[dev]`. `[tool.coverage.run]` is configured. **No `--cov-fail-under` is set** in pre-commit or any CI workflow. The infrastructure exists; the gate doesn't.

**Fix.** Add `pytest --cov=resilience_kit --cov-fail-under=85 --cov-report=xml --cov-report=term` to the unit-test CI job. Upload `coverage.xml` artefact. Add a Codecov badge to README (optional, low-effort).

**Acceptance.** A PR that drops coverage below 85% fails CI with a clear "coverage 84.x% < 85%" message.

---

### #A8 🟡 Fix or qualify the "mypy --strict clean" claim in README

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 2 · **Priority:** 1.50 · **GH:** _unfiled_ · **Status:** `fixed (already satisfied)` — audit was stale. `uv run mypy --strict src` reports *Success: no issues found in 95 source files*; `mypy.ini` already carries the per-library `ignore_missing_imports` sections; CI already has a required `types` job running it; and no literal "mypy --strict clean" overclaim exists in README. No change needed.

**Where:** `README.md` (the typing section); `mypy.ini`

**Problem.** README claims "fully typed with `py.typed` and `mypy --strict` clean." Running `uv run mypy src/` reports **35 errors** against the shipped `mypy.ini` (`strict = True`). With `--ignore-missing-imports`, **13 real errors** remain — `httpx.Auth` / `httpx.AsyncHTTPTransport` / `sqlalchemy.TypeDecorator` subclassing rejected because upstream stubs are loose; `Fernet.encrypt/decrypt` leak `Any`; FastAPI route decorators untype inner functions.

**Why this matters.** A false claim on the landing page erodes trust for any user who runs `mypy` themselves. The "fully typed" promise is half-delivered.

**Fix.** Two options:
1. **Make the claim true.** Add `[mypy-httpx.*]`, `[mypy-sqlalchemy.*]`, `[mypy-fastapi.*]`, `[mypy-redis.*]` sections with `ignore_missing_imports = True` (cuts 35 → 13). For the remaining 13, use `# type: ignore[misc]` with comment explaining upstream-stub looseness, OR refactor (e.g., use Protocol duck-typing instead of subclassing `httpx.Auth`).
2. **Qualify the claim.** Change README to "strict-mypy clean against own source; subclasses of upstream-untyped frameworks (httpx, sqlalchemy) use targeted `type: ignore`." Add `uv run mypy --strict src/` to CI as a non-blocking job (informational).

Recommended: do both — qualify in README *and* enable the missing-import ignores in `mypy.ini` so the error count drops to 0 reproducibly.

**Acceptance.** `uv run mypy --strict src/` exits 0, OR the README claim accurately reflects the current behaviour and CI runs mypy as a required check.

---

### #A9 🟢 Throttle Lua — call `redis.replicate_commands()` for Redis < 7 compatibility

**Severity:** LOW · **Impact:** 2 · **Effort:** 1 · **Priority:** 2.00 · **GH:** _unfiled_ · **Status:** `fixed` (branch `fix/lane-a-quickwins`) — chose the deterministic-counter option (`INCR key:__seq`) over `replicate_commands()`; validated against `redis:6` + `valkey:8` (allowed-flags `[1,1,1,1,1,0,0]`, zcard=5)

**Where:** `src/resilience_kit/throttle/lua_scripts.py:20-41` (SLIDING_WINDOW_LUA)

**Problem.** The sliding-window Lua uses `math.random(1000000)` to generate unique ZSET member IDs:

```lua
redis.call('ZADD', key, now, tostring(now) .. ':' .. tostring(math.random(1000000)))
```

`math.random` is non-deterministic. On Redis 3.2 – 6.x, scripts mixing `math.random` with write commands (`ZADD`) must declare `redis.replicate_commands()` at the top, or the server rejects with `Write commands not allowed after non deterministic commands`. Redis ≥ 7 makes this default but the script may still get flagged for slave-rewriting.

**Why this matters.** README claims Redis 7+ / Valkey 8+ compatibility — *technically valid* — but the script is fragile under older Valkey/Redis deployments, and the compatibility floor isn't loud in the docs.

**Fix.** Prepend `redis.replicate_commands()` to `SLIDING_WINDOW_LUA`. Or, switch the ZSET member ID to a deterministic counter: `tostring(now) .. ':' .. tostring(redis.call('INCR', key .. ':__seq'))`.

**Acceptance.** The script loads cleanly on Redis 6 (testcontainers) and continues passing the sliding-window contract suite.

---

### #A10 🟢 Add GitHub issue + PR templates

**Severity:** LOW · **Impact:** 2 · **Effort:** 1 · **Priority:** 2.00 · **GH:** _unfiled_ · **Status:** `fixed (already present)` — verified `bug_report.md` (incl. version/Python/OS/extras/backend fields), `feature_request.md` (incl. scope checklist), and `PULL_REQUEST_TEMPLATE.md` already exist and are adequate; no change needed

**Where:** `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`

**Problem.** L4 audit notes templates as present — verify. If absent: add `bug_report.md` + `feature_request.md` issue templates, plus a PR template that reproduces the ROADMAP exit-gate line as a checklist.

**Fix.** Standard GitHub templates with sections: repro / expected / actual / kit version / Python version / extras installed.

**Acceptance.** Opening a new issue on GitHub presents a populated template.

---

### Additional CI gates ported from `colending_partner` (not original audit items)

Added alongside Lane A on branch `fix/lane-a-quickwins`, mirroring the
`colending_partner/pr-checks.yml` gate set. Status: `fixed`.

- **#A11 pip-audit (OSV)** — promoted from a manual pre-commit hook to a required CI job scanning the locked runtime deps (`uv export … | pip-audit`). Surfaced 4 real CVEs on first run; remediated by bumping `cryptography`/`pydantic-settings`/`starlette`.
- **#A12 lockfile drift** — `uv lock --check` CI job; fails when `uv.lock` is out of sync with `pyproject.toml`.
- **#A13 sticky PR status comment** — `notify-pr` job renders a green/red check table on each PR via `marocchino/sticky-pull-request-comment`.
- **#A14 dead public-symbol check** — `scripts/check_dead_symbols.py` (+ pre-commit hook + CI job) flags public defs/classes with no caller and no `__all__` re-export. Found one genuine bug on first run: `cache.provider.get_cache()` crashed on every call (fixed in the same branch).
- Plus a `Makefile` exposing the full local gate (`make gate`).

---

## Lane B — v0.1.1 patch

8 correctness/security fixes, each 1-3 days. Total ~10-14 days. Resilience/security rating jumps from 7.9 → 9.2.

### #B1 🔴 SSRF redirect bypass — re-validate / re-pin on 3xx

**Severity:** CRITICAL · **Impact:** 5 · **Effort:** 2 · **Priority:** 2.50 · **GH:** _unfiled_ · **Status:** `fixed` via option 1 (branch `fix/lane-b-correctness-security`) — `pinned_httpx_client()` forces `follow_redirects=False` and raises `ValueError` on an explicit `follow_redirects=True`; added two tests to `tests/integration/test_dns_rebinding.py` (302→private not followed; opt-in refused). Per-hop re-validating handler (option 2) deferred to v0.2.

**Where:** `src/resilience_kit/http_client/{session,client,dns_pin}.py`

**Problem.** `pinned_httpx_client(**kwargs)` does not override `follow_redirects` (httpx default is `False`). If a caller passes `follow_redirects=True` to a pre-built client (legitimate ergonomic choice), httpx auto-follows 3xx responses **but the redirect's `Location` host is never re-validated through SSRF or re-pinned via DNS**. The pin is set for the *original* host; on redirect, `_pick_pinned_ip` returns `None` and the transport uses normal DNS resolution.

Concrete exploit: any public endpoint that returns `302 Location: http://169.254.169.254/latest/meta-data/` (AWS metadata) or `http://10.0.0.5/internal-api` bypasses the entire SSRF guard.

**Why this matters.** The DNS-pin TOCTOU closure is the headline feature of the http_client. The redirect path defeats it. CWE-918 (SSRF) + CWE-601 (open redirect).

**Fix.** Three options ordered by effort:
1. **Force `follow_redirects=False`** in `pinned_httpx_client`. Document that callers wanting redirects must call `resolve_and_validate()` per hop themselves. **Cheapest, safest default.**
2. **Custom redirect handler.** Subclass `httpx.AsyncClient` or hook into the redirect flow to call `resolve_and_validate(new_url)` before each follow.
3. **Document only.** Worst — preserves the footgun.

Recommended: ship #1 in v0.1.1; ship #2 as opt-in in v0.2 (`pinned_httpx_client(follow_redirects_with_revalidation=True)`).

**Acceptance.** An integration test that mocks a 302 to `http://10.0.0.5/` either (a) does not follow (#1) or (b) raises `SSRFError` (#2). Add to `tests/integration/test_dns_rebinding.py` as a sibling case.

---

### #B2 🔴 Add `Idempotency-Key` plumbing on retry POST/PUT/PATCH

**Severity:** CRITICAL · **Impact:** 5 · **Effort:** 2 · **Priority:** 2.50 · **GH:** _unfiled_

**Where:** `src/resilience_kit/retry/decorator.py`; `src/resilience_kit/http_client/client.py`

**Problem.** `@retry` / `@resilient` will happily re-execute a POST that timed out *after* the server began processing. No `Idempotency-Key` header is generated, no caller-supplied key is preserved across retries. For any fintech use case (payments, disbursements, account creation), this is the canonical double-charge bug.

**Why this matters.** Outbound payment APIs (BHN, Razorpay, Stripe) require `Idempotency-Key` for safe retry semantics. A retry library that doesn't plumb idempotency is a footgun for the exact workload it targets.

**Fix.** In `AsyncAPIClient.request()`:
1. If the caller passes `idempotency_key=<str>` (or includes `Idempotency-Key` in headers), preserve it byte-identical across every retry attempt.
2. Add an opt-in `auto_idempotency_key: bool = False` parameter that, when `True` and method is POST/PUT/PATCH, auto-generates `uuid.uuid4().hex` once at call entry and uses it for every retry attempt.
3. Document the feature in README + ADR (new ADR-0012).

For the bare `@retry` decorator (no HTTP context), document this is the caller's responsibility — the decorator cannot generate keys for arbitrary functions.

**Acceptance.** Test: a POST that raises `httpx.TimeoutException` on attempt 1 and succeeds on attempt 2 sends the same `Idempotency-Key` header on both attempts.

---

### #B3 🟠 `excluded_exceptions` non-empty default — don't open breaker on caller `ValueError`/`TypeError`

**Severity:** HIGH · **Impact:** 4 · **Effort:** 2 · **Priority:** 2.00 · **GH:** _unfiled_ · **Status:** `fixed` (branch `fix/lane-b-correctness-security`) — `DEFAULT_EXCLUDED_EXCEPTIONS = (ValueError, TypeError, KeyError, AttributeError, AssertionError)` now the `BreakerConfig` default and the `registry.py` fallback; amended ADR-0006; added a contract test asserting the default excludes `ValueError` across backends.

**Where:** `src/resilience_kit/circuit_breaker/{memory_impl,redis_impl}.py`; `BreakerConfig` dataclass

**Problem.** `BreakerConfig.excluded_exceptions: tuple[type[BaseException], ...] = ()` — empty default. The breaker catches `BaseException` minus `CancelledError` as a failure. Result: a caller raising `ValueError` for bad input opens the breaker. Business errors trip transport-failure circuit breakers.

**Why this matters.** Most application code raises `ValueError`/`TypeError`/custom domain errors that have nothing to do with the downstream service's health. Tripping the breaker on these is a false-positive open that drops legitimate traffic.

**Fix.** Default `excluded_exceptions = (ValueError, TypeError, KeyError, AttributeError, AssertionError)`. Document this is opinionated — operators with different conventions can override. Add to ADR-0006.

**Acceptance.** Test: a function that raises `ValueError` does NOT count against the breaker's failure threshold; the breaker stays CLOSED.

---

### #B4 🟠 `AuditBackend` protocol contract drift — `health_check` signature

**Severity:** HIGH · **Impact:** 4 · **Effort:** 2 · **Priority:** 2.00 · **GH:** _unfiled_

**Where:** `src/resilience_kit/audit/backends/base.py:48-78`; `docs/LLD.md` §2; `src/resilience_kit/health.py:99`

**Problem.** LLD §2 (locked protocol) specifies:

```python
async def write(self, event: AuditEvent) -> None: ...
async def write_many(self, events: Sequence[AuditEvent]) -> None: ...
async def health_check(self) -> HealthSnapshot: ...
```

Code has:

```python
async def write_many(self, events: Sequence[AuditEvent]) -> None: ...
async def health_check(self) -> bool: ...
```

Two divergences from a locked-protocol promise:
1. `write()` removed entirely — callers can no longer write a single event.
2. `health_check` returns `bool`, not `HealthSnapshot`.

`health.py:99` aggregates via `await backend.health_check()` and accesses `.healthy` on the result. If any audit backend were registered via `register_for_recovery`, the recovery monitor would crash with `AttributeError: 'bool' object has no attribute 'healthy'`. Today this is latent because audit backends don't self-register, but the protocol contract is wrong.

**Why this matters.** A third-party implementer who wrote a backend to LLD §2 fails the runtime contract. The "locked across six docs" promise is broken.

**Fix.** Either:
1. **Update LLD §2** to match the code (and document why `write` was dropped — fire-and-forget always batches).
2. **Restore the protocol shape.** Add `health_check() -> HealthSnapshot` (with a default adapter that wraps `bool` for existing backends). Add `write(self, event)` with a default impl that calls `write_many([event])`.

Recommended: option 2 — make the protocol match the documented contract. Backwards-compat shim for existing builtins.

**Acceptance.** `AuditBackend.health_check` returns `HealthSnapshot`. Both kit-shipped backends (StdlibLogging, Postgres) pass `isinstance(backend, AuditBackend)` and produce a `HealthSnapshot`. Existing tests pass.

---

### #B5 🟠 Throttle Lua — use `redis.call('TIME')` instead of client clock

**Severity:** HIGH · **Impact:** 4 · **Effort:** 2 · **Priority:** 2.00 · **GH:** _unfiled_

**Where:** `src/resilience_kit/throttle/redis_impl.py:181`; `src/resilience_kit/throttle/lua_scripts.py`

**Problem.** Client passes `self._clock.now()` as Lua `ARGV[5]`. Two pods with NTP drift of 5 seconds see different cutoffs against the same sorted-set entries; under Sentinel failover the drift can be worse. The textbook fix is to compute `now` server-side.

**Why this matters.** Cross-pod clock skew silently breaks the sliding-window invariant. A busy fleet either over-throttles (drift forward) or under-throttles (drift backward).

**Fix.** Replace the client-supplied `ARGV[5]` with `local now = tonumber(redis.call('TIME')[1])` inside the Lua. Remove the `self._clock.now()` argv. Update `FIXED_WINDOW_LUA` similarly if it has the same shape.

**Acceptance.** Integration test: two `RedisAsyncThrottle` instances with deliberately-different clocks (mocked) see consistent throttle decisions against the same Redis backend.

---

### #B6 🟠 Replace `sha256(passphrase)` KDF with PBKDF2/Argon2

**Severity:** HIGH · **Impact:** 4 · **Effort:** 2 · **Priority:** 2.00 · **GH:** _unfiled_

**Where:** `src/resilience_kit/crypto/fernet.py:96-97`

**Problem.** Current key derivation:

```python
digest = sha256(passphrase.encode()).digest()
Fernet(base64.urlsafe_b64encode(digest))
```

Unsalted, no iterations, no work factor. Secure only if `passphrase` is itself high-entropy random — which is not documented as a requirement. For human-chosen or config-file passphrases, this is brute-forceable.

**Why this matters.** CWE-916 (use of password hash with insufficient computational effort). The kit's *crypto* module is the worst-implemented crypto in the kit.

**Fix.** Two-track:
1. **Accept a raw 32-byte base64 Fernet key directly.** If `field_encryption_key` matches Fernet's expected format, use it as-is (skip the sha256 step entirely). This is the *right* primary path.
2. **For passphrase-style inputs**, use HKDF-Extract (`cryptography.hazmat.primitives.kdf.hkdf.HKDF`) with a salt drawn from a settings field `field_encryption_kdf_salt`, info=`b"resilience-kit field encryption v1"`, length=32, hash=SHA256. Document the salt requirement loudly.

For low-entropy passphrases, document that PBKDF2-HMAC-SHA256 with ≥100k iterations (or argon2) is the right tool — but the kit's path is "give us a real key."

Also: add a `field_encryption_key` validator with `min_length=32` and an entropy floor warning.

**Acceptance.** Test: a raw Fernet key passes through unchanged. A short passphrase triggers either a clear error message or HKDF with a salt. Migration doc explains how to rotate from sha256-derived keys to direct keys.

---

### #B7 🟠 `PostgresAuditBackend._ensure_pool` — `threading.Lock` does not serialise `await`

**Severity:** HIGH · **Impact:** 4 · **Effort:** 2 · **Priority:** 2.00 · **GH:** _unfiled_ · **Status:** `fixed` (branch `fix/lane-b-correctness-security`) — `_pool_lock` switched to `asyncio.Lock`; added a unit test asserting concurrent `_ensure_pool` calls create exactly one pool.

**Where:** `src/resilience_kit/audit/backends/postgres.py:118-131`

**Problem.**

```python
async def _ensure_pool(self) -> asyncpg.Pool:
    if self._pool is not None:
        return self._pool
    with self._pool_lock:                # threading.Lock — released by asyncio at await!
        if self._pool is None:
            self._pool = await asyncpg.create_pool(...)
    return self._pool
```

`threading.Lock` is released the moment `await` suspends. Two coroutines both pass the `is None` guard, both acquire the (different) stacks of the lock, both `await create_pool`, both write `self._pool`. The first pool is orphaned and never closed. `FireAndForgetDispatcher` calls `write_many` from background tasks — concurrent first-write is realistic.

**Why this matters.** Connection leak + duplicate-pool overhead on every startup race. Async-lock-vs-thread-lock is the kind of bug that takes hours to diagnose in prod.

**Fix.** Switch to `asyncio.Lock()`. Consistent with the rest of the kit.

**Acceptance.** Test: two concurrent `write_many` calls on a fresh `PostgresAuditBackend` result in exactly one `asyncpg.create_pool` invocation (mock and assert call_count == 1).

---

### #B8 🟠 Throttle fail-mode under Redis outage — document or fail-closed

**Severity:** HIGH · **Impact:** 4 · **Effort:** 2 · **Priority:** 2.00 · **GH:** _unfiled_

**Where:** `src/resilience_kit/throttle/redis_impl.py:81-88`; README; ADR (new)

**Problem.** When Redis is down, every async backend (cache/breaker/throttle/audit) follows the same `try → except RedisError → mark_degraded → fallback to in-memory` shape. This is correct for cache + breaker + audit. **It is wrong for throttle.**

A 100/min *global* throttle with 8 pods becomes effectively 800/min under a Redis outage, because each pod has its own in-memory bucket. Multiplicative blast-radius. Documented at line 6 of `redis_impl.py` ("falling back to in-memory") but the consequence is not surfaced.

**Why this matters.** Operators reasoning about "what does my rate limit do during a Redis outage?" will get the wrong answer. For payment APIs with hard upstream rate limits, this can cause cascade failure.

**Fix.** Three options:
1. **Document loudly.** Update README + add an ADR explaining the per-pod multiplier. Operators opt into the trade-off.
2. **Configurable fail-mode.** Add `ThrottleConfig.fail_mode: Literal["open", "closed"]` defaulting to `"open"` (current behaviour). `"closed"` returns `ThrottleDecision(allowed=False, reason="backend_degraded")` immediately.
3. **Both.** Document + ship the toggle.

Recommended: option 3. Default stays fail-open for ergonomics; fintech users can flip to fail-closed for hard limits.

**Acceptance.** ADR documents the per-pod multiplier. `ThrottleConfig.fail_mode` toggle ships. Test asserts both modes work.

---

## Lane C — v0.2.0 minor

6 issues. Observability becomes real; crypto rotation closed; ASGI Django finishes. Total ~3-4 weeks.

### #C1 🟠 Add `MultiFernet` + key-versioning + rotation guide

**Severity:** HIGH · **Impact:** 5 · **Effort:** 3 · **Priority:** 1.67 · **GH:** _unfiled_

**Where:** `src/resilience_kit/crypto/fernet.py`; new `docs/key-rotation.md`

**Problem.** Single-key Fernet means key rotation is a stop-the-world re-encrypt operation. For any organization with compliance requirements (PCI-DSS, ISO 27001, SOC 2), periodic key rotation is mandatory. The kit doesn't expose `cryptography.fernet.MultiFernet`.

**Why this matters.** Rotation trap — orgs that adopt the kit can't rotate without downtime. Disqualifies the library from compliance-bound deployments.

**Fix.**
1. Wrap `MultiFernet` in `FernetCipher` with key-version prefix on each token.
2. Accept `field_encryption_keys: list[SecretStr]` settings field (ordered: primary first, then older keys for decrypt-only).
3. Add `FernetCipher.rotate(plaintext_or_old_ciphertext)` helper for re-encrypting under the new primary.
4. New ADR-0012 documenting the rotation policy.
5. `docs/key-rotation.md` with operator runbook.

**Acceptance.** Test: encrypt with K1, add K2 as primary, decrypt the K1 ciphertext (still works), encrypt new data (uses K2), rotate the K1 ciphertext to K2 via `rotate()`.

---

### #C2 🟠 Add `[prometheus]` extra with `prometheus_client`-backed `MetricsSink`

**Severity:** HIGH · **Impact:** 5 · **Effort:** 4 · **Priority:** 1.25 · **GH:** _unfiled_

**Where:** New `src/resilience_kit/metrics/prometheus.py`; `pyproject.toml` `[project.optional-dependencies]`

**Problem.** Kit ships a `MetricsSink` protocol with pluggable backends. The default is a stdlib-logging shim. No `prometheus_client`-backed sink ships — operators wanting Prometheus must implement it themselves.

**Why this matters.** Observability story is half-built. Protocol without an exporter is theatre.

**Fix.**
1. Add `[prometheus]` extra: `prometheus-client>=0.19`.
2. Implement `PrometheusMetricsSink` using `Counter`, `Histogram`, `Gauge` from `prometheus_client`.
3. Wire metric names to match the kit's existing emission keys (`retry.attempt`, `retry.success`, `retry.exhausted`, `breaker.open`, `breaker.half_open`, `breaker.close`, `throttle.allowed`, `throttle.denied`, `audit.write_failed`, `audit.dropped`).
4. Register via entry point `resilience_kit.metrics_sinks = prometheus = resilience_kit.metrics.prometheus:PrometheusMetricsSink`.
5. Add operator doc with FastAPI `/metrics` endpoint recipe.

**Acceptance.** A FastAPI app with `[prometheus]` extra installed and `metrics_sink: prometheus` configured serves a working `/metrics` endpoint with kit counters incrementing on traffic.

---

### #C3 🟡 Add `[otel]` extra with OpenTelemetry SDK wiring

**Severity:** MEDIUM · **Impact:** 4 · **Effort:** 4 · **Priority:** 1.00 · **GH:** _unfiled_

**Where:** New `src/resilience_kit/metrics/otel.py`; new `src/resilience_kit/tracing/`

**Problem.** Same shape as #C2 but for OTel. Tracing is more architectural — the kit's request-id ContextVar should propagate as a span attribute; the audit dispatcher's batched flush should emit a span per batch.

**Fix.**
1. Add `[otel]` extra: `opentelemetry-api>=1.20`, `opentelemetry-sdk>=1.20`.
2. Implement `OtelMetricsSink` mapping to OTel meter API.
3. Add `TracingMiddleware` that creates a server span per request, propagates W3C `traceparent` header.
4. Inject `traceparent` outbound in `AsyncAPIClient`.
5. Document the pattern with an exporter recipe (OTLP/HTTP to a collector).

**Acceptance.** A traced inbound request → outbound HTTP call produces a connected trace in a collector (Jaeger / Tempo) with kit metrics under `resilience_kit.*`.

---

### #C4 🟡 Add `[sentry]` extra or document Sentry integration recipe

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 2 · **Priority:** 1.50 · **GH:** _unfiled_

**Where:** New `docs/sentry-integration.md`; possibly `src/resilience_kit/observability/sentry.py`

**Problem.** Most production fintech / SaaS deployments use Sentry for exception aggregation. The kit's middleware emits typed exception envelopes but doesn't wire Sentry tags / breadcrumbs natively.

**Fix.** Document the pattern (no new code needed for v0.2):
1. Show how to install `sentry-sdk[fastapi]` / `sentry-sdk[django]` alongside the kit.
2. Demonstrate adding `request_id` from the kit's `ContextVar` as a Sentry tag in the middleware order.
3. Show how to add a Sentry breadcrumb on `breaker.open` / `retry.exhausted` via a custom `MetricsSink`.

Optionally ship `[sentry]` extra with a pre-wired sink.

**Acceptance.** Doc exists. Optional: integration test in `tests/integration/test_sentry_integration.py` using `sentry_sdk.transport.HttpTransport` to a local mock.

---

### #C5 🟠 Add fintech / PII regex defaults to the audit redactor

**Severity:** HIGH · **Impact:** 4 · **Effort:** 2 · **Priority:** 2.00 · **GH:** _unfiled_

**Where:** `src/resilience_kit/audit/sanitizers.py`; possibly new `[fintech-pii]` or `[india-pii]` extra

**Problem.** `DefaultRedactor` matches only on field names (substring of lowercased key). It misses:
- Indian PII: PAN (`[A-Z]{5}[0-9]{4}[A-Z]`), Aadhaar (`\d{4}\s?\d{4}\s?\d{4}`), IFSC (`[A-Z]{4}0\d{6}`), bank account numbers (`\d{9,18}`), Indian mobile (`(\+91|0)?[6-9]\d{9}`).
- Generic PII: credit card (PAN, Luhn-valid 13-19 digits), SSN, email-in-plaintext-value, DOB patterns.

A body field named `notes` containing `"PAN: ABCDE1234F"` is logged in full.

**Why this matters.** CWE-532 in regulated environments. PCI-DSS / RBI compliance failure for Indian fintech adopters.

**Fix.**
1. Add a `RegexRedactor` (or extend `DefaultRedactor`) that scans **values** for sensitive patterns and masks them in-place.
2. Ship two pattern packs:
   - `GLOBAL_PII_PATTERNS`: credit-card-numbers (Luhn-checked), emails-in-strings, IBAN.
   - `INDIA_PII_PATTERNS`: PAN, Aadhaar (with Verhoeff validation optional), IFSC, mobile, account numbers.
3. Register both via entry points so callers can opt-in:
   ```toml
   resilience_kit.sanitizers = india_fintech = resilience_kit.audit.sanitizers:IndiaFintechRedactor
   ```
4. Document the extension recipe for regional packs (US-SSN, EU-VAT, etc.).

**Acceptance.** A test asserts that `{"notes": "PAN ABCDE1234F"}` produces `{"notes": "PAN [REDACTED]"}` when `IndiaFintechRedactor` is wired.

---

### #C6 🟠 DRF throttle ASGI compatibility — replace `asyncio.run`

**Severity:** HIGH · **Impact:** 4 · **Effort:** 3 · **Priority:** 1.33 · **GH:** _unfiled_

**Where:** `src/resilience_kit/adapters/django/drf_throttles.py:85`

**Problem.** `decision = asyncio.run(get_throttle().check(key, self._parsed_rate))` raises `RuntimeError: asyncio.run() cannot be called from a running event loop` under ASGI Django. Every DRF route decorated with a kit throttle 500's on an ASGI deployment. Contradicts ADR-0011.

**Also affects:** the breaker's per-call `asyncio.Lock` binds to whatever loop first touches it. Every DRF request creates a new loop, rebinding the lock — eventually `RuntimeError: <Lock> is bound to a different event loop`.

**Fix.** Detect running loop and bridge appropriately:
```python
try:
    loop = asyncio.get_running_loop()
    decision = asgiref.sync.async_to_sync(get_throttle().check)(key, self._parsed_rate)
except RuntimeError:
    decision = asyncio.run(get_throttle().check(key, self._parsed_rate))
```

Better: route through the daemon-thread loop that the adapter's `apps.py` already owns. Define a `_bridge_to_kit_loop(coro)` helper used by both `drf_throttles.py` and any other sync→async entry point.

Update ADR-0011 with the resolution.

**Acceptance.** A DRF view decorated with a kit throttle works under both WSGI Gunicorn and ASGI Daphne/Uvicorn deployments.

---

## Lane D — v0.3.0+ maturity

11 issues. Defer until adoption signal exists, except #D3 (bus factor) which should land sooner if a co-maintainer emerges.

### #D1 🟠 Connection-leak in `_build_redis` — own & close `Redis.from_url()` clients

**Severity:** HIGH · **Impact:** 3 · **Effort:** 3 · **Priority:** 1.00 · **GH:** _unfiled_

**Where:** `src/resilience_kit/circuit_breaker/provider.py:79`, `cache/provider.py:46`, `throttle/provider.py:44`

**Problem.** `Redis.from_url(settings.redis_url)` is called inside every backend factory. The kit's shutdown paths (`reset_*`, `monitor.stop`, FastAPI lifespan close) never call `await client.aclose()`. Each `registry.get_breaker(name)` for a new service creates a fresh `Redis` (with its own pool) and leaks the previous one on re-registration.

Also: three independent pools (cache + breaker + throttle) where one shared client would do.

**Fix.** Lift `Redis.from_url(...)` to a process-wide `get_redis_client()` in `runtime.py`. Register an `aclose` hook with the recovery monitor / lifespan. Reuse one client across sub-packages.

**Acceptance.** A `reset_all_singletons()` call followed by re-registration does not increase the open-file-descriptor count.

---

### #D2 🟡 Sync `@circuit_breaker` wrapper — `asyncio.Lock` cross-loop rebind

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 2 · **Priority:** 1.50 · **GH:** _unfiled_

**Where:** `src/resilience_kit/decorators.py:97-100`; `src/resilience_kit/circuit_breaker/memory_impl.py`

**Problem.** Every sync-wrapped call to `@circuit_breaker` runs a new event loop via `asyncio.run`. `InMemoryAsyncBreaker._lock = asyncio.Lock()` lazily binds to whatever loop first touches it. First call binds the lock to a loop that dies at the end of the call; second call lands in a new loop and tries to acquire a lock bound to the dead one → `RuntimeError: <Lock ...> is bound to a different event loop`.

The Redis breaker has the same shape (`self._sha_lock = asyncio.Lock()`).

**Fix.** Either:
1. **Refuse repeated sync use** — `@circuit_breaker` raises if it detects the breaker has been used from another loop.
2. **Lock factory pattern** — build the lock lazily inside `call()` using `asyncio.get_running_loop()` as the binding signal; recreate if previous loop is dead (the pattern `recovery.py` already uses for its `asyncio.Event`).

Option 2 is the real fix. Spreads the existing pattern from `recovery.py`.

**Acceptance.** Test: call a `@circuit_breaker("svc")`-decorated sync function from sync code twice consecutively. No `RuntimeError`.

---

### #D3 🟠 Bus-factor 1 — name a co-maintainer

**Severity:** HIGH · **Impact:** 5 · **Effort:** 4 · **Priority:** 1.25 · **GH:** _unfiled_

**Where:** New `MAINTAINERS.md`; update `CONTRIBUTING.md` + `CODEOWNERS`

**Problem.** 105 of 107 commits by one author. No external contributors. No co-maintainer. CODEOWNERS = `@prajwalmahajan101`. Most Fortune-500 procurement requires stated maintainer succession or corporate-foundation backing.

If author becomes unreachable: dependabot PRs queue indefinitely, CVEs sit in `gh security advisories` without anyone with merge rights, library forks into private custody.

**Fix.**
1. Identify a candidate co-maintainer (technical peer with public OSS history).
2. Write `MAINTAINERS.md` with named successor, escalation path, "if I'm unreachable for >30 days, @X may release security patches."
3. Grant repo admin to co-maintainer.
4. Document the protocol in CONTRIBUTING.md.

**Acceptance.** Repo has at least 2 admins with active commit access. `MAINTAINERS.md` documents the succession.

---

### #D4 🟡 Add Hypothesis property-based tests for breaker state machine

**Severity:** MEDIUM · **Impact:** 4 · **Effort:** 4 · **Priority:** 1.00 · **GH:** _unfiled_

**Where:** `tests/unit/circuit_breaker/test_state_machine_properties.py` (new)

**Problem.** `hypothesis>=6.100` is declared in `[dev]` but unused. The breaker state machine — CLOSED → OPEN → HALF_OPEN with timer-based recovery and excluded-exception filtering — is a textbook property-based-test target.

**Fix.** Write properties:
- Total-call count invariant: every transition preserves `closed_calls + open_calls == total_calls`.
- Recovery monotonicity: if `time` advances past `recovery_timeout` after the last failure, the next call admits.
- Excluded exceptions never cause state transitions.
- HALF_OPEN single-flight: with `single_flight=True`, only one concurrent call is admitted.

Use `hypothesis.stateful.RuleBasedStateMachine` for action sequences.

**Acceptance.** `hypothesis` is imported and exercised in the test tree. CI passes the property suite with default settings (≥100 examples per property).

---

### #D5 🟡 SBOM generation on release (CycloneDX)

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 2 · **Priority:** 1.50 · **GH:** _unfiled_

**Where:** `.github/workflows/release.yml`

**Problem.** No SBOM in release artefacts. Required for NIST SP 800-218 / US Executive Order 14028 procurement (US Federal customers + many Fortune-500 vendors).

**Fix.** Add `cyclonedx-py` step after `uv build`:
```yaml
- run: uvx cyclonedx-py environment -o dist/sbom-cyclonedx.json
- run: uvx cyclonedx-py environment -o dist/sbom-cyclonedx.xml --output-format xml
```
Upload as release artefacts and PyPI attestation.

**Acceptance.** Each GitHub release attaches `sbom-cyclonedx.json` and `sbom-cyclonedx.xml`.

---

### #D6 🟡 Signed releases (Sigstore / cosign attestations)

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 3 · **Priority:** 1.00 · **GH:** _unfiled_

**Where:** `.github/workflows/release.yml`

**Problem.** `pypa/gh-action-pypi-publish` supports `attestations: true` (Sigstore-signed). The kit doesn't enable it. SLSA-3 baseline for supply-chain integrity requires signed provenance.

**Fix.** Add `attestations: true` to the `pypa/gh-action-pypi-publish` step. Confirm OIDC token has the required scope. Document the verification recipe in `SECURITY.md` (operator can verify the sigstore bundle on PyPI).

**Acceptance.** PyPI release page shows "Sigstore signed" badge. `pip download resilience-kit --require-hashes` succeeds; bundle verification via `sigstore verify` succeeds.

---

### #D7 🔵 Add Flask adapter

**Severity:** ECOSYSTEM · **Impact:** 4 · **Effort:** 5 · **Priority:** 0.80 · **GH:** _unfiled_

**Where:** New `src/resilience_kit/adapters/flask/`; new `src/resilience_kit/middleware/wsgi/`

**Problem.** Kit ships ASGI middleware only. Flask is WSGI. ROADMAP M9 noted "WSGI mirrors land alongside Flask adapter" — never delivered.

**Fix.** ~150 LOC of WSGI middleware (mirroring six ASGI classes) + ~100 LOC of Flask adapter (lifecycle wrapper via `before_first_request`/`teardown_appcontext`, `errorhandler` bridge, blueprint with `/healthz`/`/readyz`).

**Acceptance.** A Flask app installs `resilience-kit[flask]`, wires `init_resilience(app)`, and gets `/healthz`/`/readyz` + request-id middleware + rate-limit headers.

---

### #D8 🔵 Add Celery adapter

**Severity:** ECOSYSTEM · **Impact:** 3 · **Effort:** 4 · **Priority:** 0.75 · **GH:** _unfiled_

**Where:** New `src/resilience_kit/adapters/celery/`

**Problem.** No native Celery integration. `@retry` + `@circuit_breaker` work on Celery tasks but the task lifecycle (signals, soft-timeout, task-id propagation) isn't wired into the kit's ContextVar discipline.

**Fix.** Adapter that:
1. Propagates `request_id` from caller into task headers, restores on task entry.
2. Wires `task_failure` / `task_retry` signals into the kit's audit dispatcher.
3. Provides `@resilient_task` decorator combining `@app.task` + `@resilient(name)`.

**Acceptance.** A Celery task decorated `@resilient_task("downstream-api")` propagates request-id and emits audit events on failure.

---

### #D9 🔵 Add `resilience-kit doctor` CLI

**Severity:** ECOSYSTEM · **Impact:** 3 · **Effort:** 5 · **Priority:** 0.60 · **GH:** _unfiled_

**Where:** New `src/resilience_kit/cli/`; `pyproject.toml` `[project.scripts]`

**Problem.** Operators landing on the kit have no quick health-check. A `doctor` CLI that validates settings, probes Redis/Postgres connectivity, lists discovered backends, and dumps the effective config would dramatically reduce onboarding friction.

**Fix.** Click/Typer-based CLI:
- `resilience-kit doctor` — full health probe.
- `resilience-kit list-backends` — show resolved backends per subsystem.
- `resilience-kit settings` — dump effective config (redacted).
- `resilience-kit migrate-key --from=<sha256-key> --to=<fernet-key>` — once #C1 lands.

**Acceptance.** `resilience-kit doctor` exits 0 on a correctly-configured dev environment and exits 1 with actionable diagnostics on a misconfigured one.

---

### #D10 🔵 Hosted documentation site (Sphinx or MkDocs)

**Severity:** ECOSYSTEM · **Impact:** 3 · **Effort:** 4 · **Priority:** 0.75 · **GH:** _unfiled_

**Where:** New `docs/` site config; GitHub Pages workflow

**Problem.** `py.typed` + mypy-strict-clean codebase begs for auto-generated API reference. ROADMAP v0.4 parks "Sphinx + mkdocs-material."

**Fix.** MkDocs-material with `mkdocstrings[python]` for auto-API. Configure GitHub Pages publish via existing release.yml hook. Use existing `docs/*.md` as the navigation tree.

**Acceptance.** `https://prajwalmahajan101.github.io/resilience-kit/` (or custom domain) serves rendered docs.

---

### #D11 🔵 Announcement post + adoption signal

**Severity:** ECOSYSTEM · **Impact:** 4 · **Effort:** 2 · **Priority:** 2.00 · **GH:** _unfiled_

**Where:** External — Hashnode / dev.to / Medium; cross-link from README

**Problem.** Library has 1 star and minimal PyPI download count. The work is in the 95th percentile of solo Python OSS; the discoverability is in the 5th. **The marketing/discoverability gap is the only dimension where a senior reviewer would say "why did you build this and not promote it?"**

**Fix.** Ship the planned post: *"Circuit-breaker placement is different in async than sync — here's why."* Include:
1. The ServiceUnavailableError-filter design (the quietly-excellent piece).
2. The DNS-pin TOCTOU closure with the integration test as proof.
3. The protocol-not-ABC trade-off (ADR-0001).
4. A working FastAPI example.

Cross-post: HackerNews `Show HN`, Reddit `r/Python`, Lobste.rs.

**Acceptance.** Post live. README links it. Repo has ≥10 stars from non-author sources within 30 days, OR explicit feedback identifies why the framing failed.

---

## Snapshot table — all 35 issues

> **Lane A status (2026-06-29):** all 10 Lane A items closed on branch
> `fix/lane-a-quickwins` (#A8 and #A10 were already satisfied; the rest fixed).
> Four extra CI gates (#A11–#A14) + a Makefile were ported from
> `colending_partner`. See each issue's **Status** line above for detail. The
> `GH` column below is unchanged — it tracks GitHub issue numbers, still unfiled.


| ID | Severity | Title | Impact | Effort | Priority | Lane | GH |
|---|:---:|---|:---:|:---:|:---:|:---:|---|
| #A1 | 🟡 | Cookie / Set-Cookie redaction | 3 | 1 | 3.00 | A | _-_ |
| #A2 | 🟡 | Remove dead `__acall__` | 3 | 1 | 3.00 | A | _-_ |
| #A3 | 🟡 | ADR-0009 vs ADR-0004 reconcile | 3 | 1 | 3.00 | A | _-_ |
| #A4 | 🟢 | Alpha → Beta classifier | 2 | 1 | 2.00 | A | _-_ |
| #A5 | 🟢 | Dependabot automerge | 2 | 1 | 2.00 | A | _-_ |
| #A6 | 🟢 | CODE_OF_CONDUCT.md | 1 | 1 | 1.00 | A | _-_ |
| #A7 | 🟡 | --cov-fail-under gate | 3 | 1 | 3.00 | A | _-_ |
| #A8 | 🟡 | Fix mypy-strict README claim | 3 | 2 | 1.50 | A | _-_ |
| #A9 | 🟢 | Throttle Lua replicate_commands | 2 | 1 | 2.00 | A | _-_ |
| #A10 | 🟢 | Issue + PR templates | 2 | 1 | 2.00 | A | _-_ |
| #B1 | 🔴 | SSRF redirect bypass | 5 | 2 | 2.50 | B | _-_ |
| #B2 | 🔴 | Idempotency-Key plumbing | 5 | 2 | 2.50 | B | _-_ |
| #B3 | 🟠 | excluded_exceptions default | 4 | 2 | 2.00 | B | _-_ |
| #B4 | 🟠 | AuditBackend protocol drift | 4 | 2 | 2.00 | B | _-_ |
| #B5 | 🟠 | Throttle redis.call('TIME') | 4 | 2 | 2.00 | B | _-_ |
| #B6 | 🟠 | Replace sha256 KDF | 4 | 2 | 2.00 | B | _-_ |
| #B7 | 🟠 | Postgres pool await-under-lock | 4 | 2 | 2.00 | B | _-_ |
| #B8 | 🟠 | Throttle fail-mode toggle | 4 | 2 | 2.00 | B | _-_ |
| #C1 | 🟠 | MultiFernet + rotation | 5 | 3 | 1.67 | C | _-_ |
| #C2 | 🟠 | Prometheus exporter | 5 | 4 | 1.25 | C | _-_ |
| #C3 | 🟡 | OTel SDK extra | 4 | 4 | 1.00 | C | _-_ |
| #C4 | 🟡 | Sentry integration | 3 | 2 | 1.50 | C | _-_ |
| #C5 | 🟠 | Fintech/PII redactor pack | 4 | 2 | 2.00 | C | _-_ |
| #C6 | 🟠 | DRF throttle ASGI | 4 | 3 | 1.33 | C | _-_ |
| #D1 | 🟡 | Redis connection ownership | 3 | 3 | 1.00 | D | _-_ |
| #D2 | 🟡 | Sync breaker lock rebind | 3 | 2 | 1.50 | D | _-_ |
| #D3 | 🟠 | Bus factor — co-maintainer | 5 | 4 | 1.25 | D | _-_ |
| #D4 | 🟡 | Hypothesis property tests | 4 | 4 | 1.00 | D | _-_ |
| #D5 | 🟡 | SBOM on release | 3 | 2 | 1.50 | D | _-_ |
| #D6 | 🟡 | Sigstore signed releases | 3 | 3 | 1.00 | D | _-_ |
| #D7 | 🔵 | Flask adapter | 4 | 5 | 0.80 | D | _-_ |
| #D8 | 🔵 | Celery adapter | 3 | 4 | 0.75 | D | _-_ |
| #D9 | 🔵 | doctor CLI | 3 | 5 | 0.60 | D | _-_ |
| #D10 | 🔵 | Hosted docs site | 3 | 4 | 0.75 | D | _-_ |
| #D11 | 🔵 | Announcement post | 4 | 2 | 2.00 | D | _-_ |

---

## How to use this file

1. **Triage:** read the snapshot table, pick a lane.
2. **File on GitHub:** open issues for Lane A + Lane B first (18 issues). Copy the issue body from the corresponding `#ID` section.
3. **Backfill `GH:`:** replace `_unfiled_` / `_-_` with `#NN` once filed.
4. **Update status on close:** the PR that fixes an issue must touch this file in the same commit — change `_unfiled_` → `fixed in #PR` and add a `**Fixed in:**` line.
5. **Cross-link from CHANGELOG:** when cutting v0.1.1, list every `fixed` issue from this file.

---

## Source audits

This catalog is the consolidated view of:

- `audit/RKIT-L1-code-quality.md` — implementation correctness (B+, 7.8/10)
- `audit/RKIT-L2-architecture.md` — protocol & design discipline (7.6/10)
- `audit/RKIT-L3-resilience-security.md` — primitives + threat model (7.9/10)
- `audit/RKIT-L4-process-release.md` — engineering process (8.6/10)
- `audit/NEXT-STEPS-gaps-and-adoption.md` — coverage gaps + adoption sequencing
- `audit/RATINGS-and-impact-effort.md` — impact-vs-effort scoring (canonical)
- `audit/PRAISE-vs-GRILL-and-engineer-read.md` — paired praise/critique

Last updated: 2026-06-24.
