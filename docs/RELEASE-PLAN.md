# Release plan — `resilience-kit` v0.1.0 final and beyond

> **Purpose.** Status dashboard + decision document for the M8b → v0.1.0
> final cycle and the post-0.1.0 version plan. Lives alongside
> [ROADMAP.md](./ROADMAP.md) (long-form version planning) and
> [MIGRATION-from-boilerplate-embedded.md](./MIGRATION-from-boilerplate-embedded.md)
> (adopter guide). This doc is the *executable* view: what's in flight,
> what's waiting on whom, what lands before v0.1.0 ships.
>
> **Owner.** Solo project. Refresh on every M8b PR merge.

---

## 1. Status snapshot

### 1.1 In flight — open PRs on `feat/m8b-*` branches

| PR | Branch | Scope | Blocking v0.1.0? | Review state |
|---|---|---|---|---|
| [#15](https://github.com/prajwalmahajan101/resilience-kit/pull/15) | `feat/m8b-issue-002-forbid` | `extra="forbid"` on `ResilienceSettings` — breaking inside 0.1.x, MUST land before 0.1.0 | **🔴 yes** | awaiting CI + merge |
| [#17](https://github.com/prajwalmahajan101/resilience-kit/pull/17) | `feat/m8b-docs` | `SECURITY.md`, `CONTRIBUTING.md`, ADRs 0001/2/3/4/6, README sync | 🟡 docs polish | awaiting CI + merge |
| [#18](https://github.com/prajwalmahajan101/resilience-kit/pull/18) | `feat/m8b-arch-followups-003-005` | ISSUE-003 bytes coerce + ISSUE-004/005 docs | 🟢 no | awaiting CI + merge |
| [#16](https://github.com/prajwalmahajan101/resilience-kit/pull/16) | `feat/m8b-release-workflow` | `.github/workflows/release.yml` (PyPI Trusted Publishing) | 🟡 cuts the release | awaiting CI + merge |
| [#19](https://github.com/prajwalmahajan101/resilience-kit/pull/19) | `feat/m8b-roadmap-v0.2-plus` | `docs/ROADMAP.md` post-dogfooding version slots | 🟢 no | awaiting CI + merge |
| [#20](https://github.com/prajwalmahajan101/resilience-kit/pull/20) | `feat/m8b-migration-post-dogfooding` | `MIGRATION.md` §10 + adapter docstring warnings + CHANGELOG | 🟡 docs polish | awaiting CI + merge |

### 1.2 Waiting on you (manual action)

| Task | Why it's blocking | Source |
|---|---|---|
| **Configure PyPI Trusted Publisher** at <https://pypi.org/manage/account/publishing/> with `prajwalmahajan101 / resilience-kit / release.yml / pypi` environment | First-run of `release.yml` for `v0.1.0` cut needs this; without it, the `publish-pypi` job fails with an OIDC auth error | PR #16 body |
| **Decide which dogfooding items land *before* v0.1.0** (§3 below) | The default in current ROADMAP is "all in v0.1.x patch line"; the dogfooding reports argue some of them should ship pre-cut | This plan, §3 |
| **Triage CI failures** if any PR turns red | Pre-existing darglint / mypy noise on `main` may resurface | PR #17 + #20 |

### 1.3 Waiting on external work

| Task | Source | Status |
|---|---|---|
| ~~FastAPI M7 boilerplate integration report~~ | `fastapi_boilerplate/docs/m7-*-report.md` | ✅ delivered (7.5/10) |
| ~~Django M7 boilerplate integration report~~ | `django_boilerplate/docs/m7-outcome-report.md` | ✅ delivered (8.4–8.6/10) |
| M7 boilerplate PRs (`feat/depend-on-resilience-kit` in both repos) merged to their `main` | M7 ROADMAP exit gate | 🟡 in flight |
| Both boilerplates re-pinned to `==0.1.0` after the kit cut | Section E of M8b plan | ⛔ blocked on kit `v0.1.0` cut |

---

## 2. Recommended next action (single highest-leverage)

**Land the five cheap adopter-ergonomics helpers in a new branch (`feat/m8b-pre-cut-ergonomics`) and ship them inside v0.1.0**, instead of deferring all of them to the v0.1.x patch line.

Rationale: the dogfooding reports explicitly suggest the kit "ship even
half of the §4 'better to have' list before M8 locks in 0.1.0" (Django
report §6). The cheap helpers below total ~150 LOC + tests, are all
additive (non-breaking), and remove the friction points that scored
each adopter's biggest regressions. Landing them pre-cut converts a
"defensible decision with three known sharp edges" (Django report §6)
into "an obviously-correct decision a year from now."

See §3 for the per-item triage.

---

## 3. Pre-cut triage — what should land *before* v0.1.0?

The default in `ROADMAP.md` is "all dogfooding items on the v0.1.x
patch line." This section re-evaluates each item against three
criteria: **cost** (LOC + design complexity), **impact** (how badly the
report flagged the gap), and **breaking risk** (additive vs API
change). Items that score cheap + high-impact + non-breaking move into
v0.1.0.

### 3.1 ✅ Landed pre-0.1.0 (D1 approved 2026-06-11)

| # | Item | Cost | Why pre-cut | Origin |
|---|---|---|---|---|
| A | **`resilience_kit.context.bind_to(consumer_ctxvar)`** | ~20 LOC + 2 tests | Closes the silent-null `request_id` footgun the FastAPI report ranked as its **#1 high-severity finding**. Costs nothing to ship. | FastAPI §0.1 |
| B | **`reset_all_singletons_async()`** | ~10 LOC + 1 test | Sync-vs-async drift that costs every test harness ~20 minutes to debug post-migration. Trivial. | FastAPI §3.3 / Report-2 §wishlist-3 |
| C | **`verify_envelope_contract()`** pytest helper | ~50 LOC + tests | Pins the `BaseCustomError(ResilienceKitError)` invariant the Django report called "load-bearing with no test today." Lets every adopter assert their bridge survives refactors. | Django §3.6 + §4.5 |
| D | **`from_exception(exc, *, envelope_cls=None)`** helper | ~30 LOC + 2 tests | Option-3 fix for the envelope-collision trap the FastAPI report ranked as its **#2 high-severity finding**. Lets adopters keep their existing wire shape with a single import. | FastAPI §0.2 + Report-2 §wishlist-4 |
| E | **`legacy_env_alias()`** translator | ~40 LOC + an env-alias table + 3 tests | Removes the silent operator-tuning loss every deploy hits on the env-var rename. Caller-side opt-in, no auto-magic; doc-linked from MIGRATION §10.5. | Django §3.3 + §4.6 |

**Total**: ~150 LOC + ~10 tests. One new branch
`feat/m8b-pre-cut-ergonomics`. Estimated effort: half a day.

Each one is independently shippable; if any becomes contentious during
review, drop it back to the v0.1.x patch line without blocking the
others.

### 3.2 Pre-cut helper task breakdowns

Each block lists files touched, signature, test cases, and acceptance
criteria. Items are scoped so they can ship in parallel or be picked
individually.

#### Helper A — `resilience_kit.context.bind_to(consumer_ctxvar)`

- **Files**: `src/resilience_kit/context.py` (new function + `__all__`); `tests/unit/test_context.py` (new tests).
- **Signature**:
  ```python
  def bind_to(target: ContextVar[str | None]) -> ContextManager[None]:
      """Mirror resilience_kit.context.request_id into ``target`` for the duration of the block."""
  ```
- **Implementation**: simple `@contextmanager` that snapshots `request_id.get()`, sets `target.set(value)`, restores both on exit. Idempotent if `target is request_id`.
- **Tests**:
  - `test_bind_to_copies_request_id` — sets `request_id` to a value, `bind_to(target)` mirrors it, target reads same value inside the block.
  - `test_bind_to_restores_on_exit` — target reads back to its prior value after the block.
- **Acceptance**: `from resilience_kit.context import bind_to` works; tests pass; module docstring of `context.py` references it.
- **Effort**: S (≤ 1 hr).
- **Dependencies**: none.

#### Helper B — `reset_all_singletons_async()`

- **Files**: `src/resilience_kit/testing/reset.py` (new function); `tests/unit/testing/test_reset.py` (new test).
- **Signature**:
  ```python
  async def reset_all_singletons_async() -> None:
      """Async wrapper around reset_all_singletons() so test harnesses with async fixtures don't need to_thread."""
  ```
- **Implementation**: one-line `reset_all_singletons()` call. The kit's sync function is non-blocking; the async wrapper is purely an ergonomic shim. Document in the function's docstring that no actual await happens internally.
- **Tests**: `test_reset_all_singletons_async_clears_state` — async-fixture-style usage; assert post-call state is reset.
- **Acceptance**: `from resilience_kit.testing.reset import reset_all_singletons_async` works; test passes.
- **Effort**: S (≤ 30 min).
- **Dependencies**: none.

#### Helper C — `verify_envelope_contract()` pytest helper

- **Files**: `src/resilience_kit/testing/contract.py` (new module); `tests/unit/testing/test_contract.py` (self-tests).
- **Signature**:
  ```python
  def verify_envelope_contract(
      *,
      handler: Callable[[Exception], Any],          # adopter's exception handler
      envelope_schema: Callable[[dict[str, Any]], None],  # adopter's pydantic / TypedDict validator
      exceptions: Sequence[type[ResilienceKitError]] = DEFAULT_KIT_EXCEPTIONS,
  ) -> None:
      """Assert that ``handler`` returns an ``envelope_schema``-shaped dict for every kit exception class."""
  ```
- **Implementation**: instantiate each kit exception class with minimal kwargs, route through the adopter's handler, validate the returned dict (or `JSONResponse.body` decoded) against `envelope_schema`. Collects all failures into one `AssertionError` so a CI failure tells the maintainer *every* shape that broke, not just the first.
- **Tests**: 
  - `test_verify_envelope_contract_passes_for_default_kit_handler` — wire up the kit's own `install_exception_handlers` + LLD §11 schema.
  - `test_verify_envelope_contract_reports_all_failing_exceptions` — pass a deliberately broken handler, assert the error message names every broken class.
- **Acceptance**: pytest plugin not required; works as a plain helper an adopter imports in their own test suite.
- **Effort**: M (~2 hr including handler/schema interop).
- **Dependencies**: none.

#### Helper D — `from_exception(exc, *, envelope_cls=None)`

- **Files**: `src/resilience_kit/adapters/_envelope.py` (new shared module — both adapters import from here); `src/resilience_kit/adapters/fastapi/exception_handlers.py` (refactor `_envelope` to delegate); `tests/unit/adapters/test_from_exception.py` (new tests).
- **Signature**:
  ```python
  def from_exception(
      exc: ResilienceKitError,
      *,
      envelope_cls: type[BaseModel] | None = None,
      include_request_id: bool = True,
      extra_headers: Mapping[str, str] | None = None,
  ) -> tuple[dict[str, Any], int, dict[str, str]]:
      """Build (body, status, headers) for ``exc``. If ``envelope_cls`` is given, fields are mapped via its model_fields; otherwise the LLD §11 shape is returned."""
  ```
- **Implementation**: extract the body/status/headers logic out of the FastAPI `_envelope` helper into a framework-agnostic function. When `envelope_cls` is given, project `error_code` / `message` / `details` onto whichever field names the envelope's `model_fields` declares (look for `error_code`, `code`, `error`, `errors`, `message`, `detail`, `details`, `request_id`).
- **Tests**:
  - `test_from_exception_default_envelope` — returns LLD §11 shape.
  - `test_from_exception_with_custom_envelope_cls` — projects onto a `{success, message, errors[], request_id}` pydantic model.
  - `test_from_exception_rate_limit_includes_retry_after_header` — `RateLimitError` adds `Retry-After` + `X-RateLimit-*` to the headers tuple.
- **Acceptance**: refactor leaves the existing FastAPI envelope path identical (same JSON output); new helper documented in MIGRATION §10.2 as the "Option 3" fix.
- **Effort**: M (~3 hr including envelope-cls projection logic).
- **Dependencies**: none. Helper E and D can both reuse `_envelope.py`.

#### Helper E — `legacy_env_alias()` translator

- **Files**: `src/resilience_kit/runtime.py` (new function + alias table constant); `tests/unit/test_runtime.py` (extend existing).
- **Signature**:
  ```python
  def legacy_env_alias(
      *,
      env: MutableMapping[str, str] = os.environ,
      aliases: Mapping[str, str] = DEFAULT_ALIASES,
      warn: bool = True,
  ) -> dict[str, str]:
      """Copy legacy env-var values onto their RESILIENCE_* equivalents. Returns the mapping of legacy→new pairs that were translated. Emits one DeprecationWarning per alias used (if warn=True)."""
  ```
- **Alias table** (≥10 entries; mirrors MIGRATION §10.5):
  ```python
  DEFAULT_ALIASES = {
      "FIELD_ENCRYPTION_KEY": "RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY",
      "REDIS_URL": "RESILIENCE_REDIS_URL",
      "OUTBOUND_ALLOWLIST": "RESILIENCE_SSRF__OUTBOUND_ALLOWLIST",
      "RATE_LIMIT_ANON": "RESILIENCE_DEFAULTS__THROTTLE__ANON_RATE",
      "RATE_LIMIT_AUTH": "RESILIENCE_DEFAULTS__THROTTLE__AUTH_RATE",
      "RATE_LIMIT_BURST": "RESILIENCE_DEFAULTS__THROTTLE__BURST_RATE",
      "CIRCUIT_BREAKER_FAIL_MAX": "RESILIENCE_DEFAULTS__CIRCUIT_BREAKER__FAIL_MAX",
      "CIRCUIT_BREAKER_RESET_TIMEOUT": "RESILIENCE_DEFAULTS__CIRCUIT_BREAKER__RESET_TIMEOUT",
      "RECOVERY_PROBE_INTERVAL": "RESILIENCE_RECOVERY__PROBE_INTERVAL_SECONDS",
      "AUDIT_SINK": "RESILIENCE_AUDIT__SINK",
  }
  ```
- **Tests**:
  - `test_legacy_env_alias_copies_value` — sets `FIELD_ENCRYPTION_KEY`, calls helper, asserts `RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY` now has the same value.
  - `test_legacy_env_alias_does_not_overwrite_new_name` — if both names are set, the new name wins; helper warns but does not overwrite.
  - `test_legacy_env_alias_emits_deprecation_warning` — `pytest.warns(DeprecationWarning, match="FIELD_ENCRYPTION_KEY")`.
- **Acceptance**: documented in MIGRATION §10.5 as the recommended bridge for one release; CHANGELOG entry warns it is **opt-in** (the caller has to import + call it in their settings module).
- **Effort**: S (~1.5 hr).
- **Dependencies**: none.

#### Coordination notes for the bundle

- All five helpers live behind imports that already exist (no new top-level `resilience_kit.*` names without ADR review).
- Each helper gets a `[Unreleased] → [0.1.0]` CHANGELOG bullet citing the originating dogfooding finding.
- README does **not** need a section bump — the helpers are documented inline at their import path and through MIGRATION §10.
- Pre-commit / mypy clean before push; no `--no-verify` use.

### 3.2 🟡 Optionally consider for v0.1.0 (case-by-case)

| Item | Cost | Argument for pre-cut | Argument against |
|---|---|---|---|
| **FastAPI `create_health_router()` / `create_readiness_router()`** | ~80 LOC + tests | Net-new feature, zero breaking surface, every FastAPI adopter hand-rolls it. Highest "what would make it 9/10" item per FastAPI Report-2. | Larger surface than the §3.1 cheap five; needs care around `app.include_router(...)` semantics. |
| **`AuthType` deprecation shim** | ~15 LOC | One-release courtesy for anyone whose codebase still uses the enum after M7. | If no downstream still uses it post-M7, it's dead code. Verify there's an actual caller before shipping. |

### 3.3 ❌ Recommend deferring to post-0.1.0

| Item | Why defer | Target |
|---|---|---|
| **`MetricsSink` cardinality contract** | Best as a Protocol upgrade — breaking surface needs careful design + adopter migration period. Land in v0.2 with the breaking tag and a migration guide. | v0.2 |
| **Real `DjangoSettingsSource`** | ~150 LOC, needs design for how the `RESILIENCE` dict maps onto `ResilienceSettings` (per-key vs whole-tree). Worth taking time on. | v0.2 |
| **`GlobalThrottle`** | Lua scripting + new throttle backend type. ~120 LOC kit + script versioning. | v0.2 |
| **Multi-alias Redis** | Settings schema change (`redis_url: str` → `redis_urls: dict[str, str]`). Breaking in 0.1.x. | v0.3 |
| **`HTTPAuditEvent` subclass** | Audit shape change; needs careful coordination with adopters who kept their own audit pipeline. | v0.3 |
| **`AsyncFernetCipher`** | Additive but not blocking — current sync class works fine inside `asyncio.to_thread`. | v0.3 |
| **Free-function metrics shim** | Lands alongside the cardinality contract. | v0.2 |
| **Shared utility modules** | ~600 LOC of kit-side code, ~900 LOC adopter-side dedup. Big enough to deserve its own milestone. | v0.3 |
| **`backend_name` + `reset_backend(alias)`** | Diagnostic API; not on the hot path. | v0.3 |
| **`tasks.local_queue` rename** | Breaking inside v0.2 anyway — no value in pre-shipping. | v0.2 |
| **Flask + Celery + Litestar adapters** | Net-new framework support; not v0.1 scope. | v0.2 / v0.3 |
| **`doctor` CLI** | Tooling, not protocol. | v0.3 |
| **Sphinx site** | Visibility, not functionality. | v0.4 |

---

## 4. v0.1.0 cut workflow

Run in order once §1 PRs are merged and §3.1 helpers (if pursued) land.

```bash
# 1. Sync main and confirm everything's in.
git switch main && git pull --ff-only
git log --oneline -15   # all six (or seven) PRs visible

# 2. Triage the dogfooding reports one more time — anything new since §3.1?
test -f /home/prjawal/Desktop/git_projects/office/Projects/django_boilerplate/docs/m7-outcome-report.md
test -f /home/prjawal/Desktop/git_projects/office/Projects/fastapi_boilerplate/docs/m7-kit-integration-report.md

# 3. Bump version.
sed -i 's|^__version__ = .*|__version__ = "0.1.0"|' src/resilience_kit/_version.py

# 4. Flip CHANGELOG [Unreleased] → [0.1.0] with the rc1→0.1.0 deltas.
#    (Manual edit; collapse §3.1 helpers + the dogfooding doc work into the new section.)

# 5. Verify the build still works.
uv build && uv tool run twine check --strict dist/*
uv run pytest tests/unit -q
uv run pytest tests/contract -q

# 6. Confirm PyPI Trusted Publisher is configured (§1.2).
#    Without this, the publish job fails — fix on PyPI side, not in code.

# 7. Cut the release.
git switch -c release/v0.1.0
git add src/resilience_kit/_version.py CHANGELOG.md
git commit -m "release: v0.1.0 final"
git push -u origin release/v0.1.0
gh pr create --title "release: v0.1.0 final" --body "..."
# merge once green

git switch main && git pull --ff-only
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0    # release.yml takes over from here

# 8. Watch the run.
gh run watch
```

After the workflow finishes:

- [ ] PyPI shows `0.1.0` as the latest (non-pre-release) version.
- [ ] GitHub Release `v0.1.0` exists, **not** marked pre-release, with CHANGELOG-extracted notes and `dist/*` attached.
- [ ] `pip install resilience-kit` (no version pin) on a clean venv installs `0.1.0` and `import resilience_kit; print(rk.__version__)` prints `0.1.0`.
- [ ] README install commands flip away from the `==0.1.0rc1` pin.
- [ ] Open follow-up PRs in both boilerplates to re-pin from `==0.1.0rc1` → `==0.1.0`, applying the relevant recipes from [`MIGRATION-rc1-to-v0.1.0.md` §3](./MIGRATION-rc1-to-v0.1.0.md#3-blocker--helper-recipes) and filing the §5 migration report.

---

## 5. v0.1.x patch line (post-0.1.0, additive only)

Items that didn't make the pre-cut bar in §3.1 land here, one or two
per minor version, no breaking changes. Cut whenever there's a reason
to (a security advisory, a downstream blocker, accumulated polish).
See [ROADMAP.md](./ROADMAP.md#v01x-patch-line--additive-non-breaking)
for the canonical list.

### 5.1 Ordered ship plan

| Order | Item | Target | Effort |
|---|---|---|---|
| 1 | **FastAPI healthcheck routers** — `create_health_router()` / `create_readiness_router()` | v0.1.1 | M |
| 2 | **`AuthType` deprecation shim** | v0.1.2 *(skip entirely if no caller still uses the enum)* | S |

If `MetricsSink` cardinality work (currently planned for v0.2) takes
longer than expected, the **free-function metrics shim** (`record_*`
helpers without the cardinality contract) can land as a v0.1.x patch
as a tactical workaround.

### 5.2 v0.1.x task breakdowns

#### v0.1.1 — FastAPI healthcheck routers

- **Files**: `src/resilience_kit/adapters/fastapi/health.py` (new); `src/resilience_kit/adapters/fastapi/__init__.py` (export both names); `tests/unit/adapters/test_fastapi_health.py` (new); `tests/integration/fastapi_app/` (extend existing app to use the new routers).
- **Signatures**:
  ```python
  def create_health_router(
      *,
      prefix: str = "",
      include_in_schema: bool = False,
      tags: Sequence[str] = ("health",),
  ) -> APIRouter:
      """APIRouter with GET /healthz always returning 200."""

  def create_readiness_router(
      *,
      prefix: str = "",
      include_in_schema: bool = False,
      tags: Sequence[str] = ("health",),
      probes: Sequence[Callable[[], Awaitable[HealthSnapshot]]] | None = None,
  ) -> APIRouter:
      """APIRouter with GET /readyz aggregating health_snapshot() + optional adopter probes."""
  ```
- **Implementation notes**:
  - Move the routes currently in `install_health_routes(app)` into the routers; keep `install_health_routes` working as a thin wrapper around `app.include_router(create_health_router())` for backwards compatibility.
  - Adopter-supplied probes run *in addition* to kit-registered backends. Each probe must return a `HealthSnapshot`; readiness is "any probe degraded → 503."
- **Tests**:
  - `test_create_health_router_returns_200` — mount on FastAPI app, hit `/healthz`.
  - `test_create_readiness_router_returns_503_when_kit_backend_degraded` — kill a fake backend's `health_check`.
  - `test_create_readiness_router_aggregates_adopter_probes` — adopter probe returns degraded → 503; both probes healthy → 200.
- **Acceptance**: existing `install_health_routes(app)` still works (regression-free); new routers documented in MIGRATION §10.3 as the replacement for hand-rolled boilerplate routers.
- **Effort**: M (~4 hr including integration test).
- **Dependencies**: none.

#### v0.1.2 — `AuthType` deprecation shim *(conditional)*

- **Decision gate**: run `gh search code --owner prajwalmahajan101 'AuthType'` (and any other repos that depend on the kit). If zero results post-M7, skip this item entirely.
- **Files**: `src/resilience_kit/http_client/auth.py` (add module-level `__getattr__` for `AuthType`); `tests/unit/http_client/test_auth.py` (deprecation-warning test).
- **Signature** (lazy attribute):
  ```python
  def __getattr__(name: str) -> Any:
      if name == "AuthType":
          warnings.warn(
              "AuthType enum dispatch is deprecated; use BasicAuth, BearerAuth, "
              "or HMACAuth classes directly.",
              DeprecationWarning,
              stacklevel=2,
          )
          return _AuthType_legacy_enum
      raise AttributeError(...)
  ```
- **Tests**: `test_authtype_emits_deprecation_warning_on_first_access`.
- **Acceptance**: existing callers continue to work; new warning fires; shim removed in v0.3.
- **Effort**: S (~1 hr).
- **Dependencies**: none.

---

## 6. v0.2 plan — "adopter ergonomics" (target: ~6 weeks post-0.1.0)

Theme: close the three biggest *needed-this-in-production* gaps the
FastAPI dogfooding flagged, plus the two new framework adapters that
were on the original v0.1 punt list.

### 6.1 Ordered ship plan

| Order | Item | Effort | Breaking? |
|---|---|---|---|
| 1 | **`MetricsSink` cardinality contract** + free-function shim | M-L | yes (Protocol upgrade) |
| 2 | **Real `DjangoSettingsSource`** | M | no (additive) |
| 3 | **`GlobalThrottle`** Valkey-Lua system-wide cap | M | no (additive) |
| 4 | **Flask adapter** | L | no (new package) |
| 5 | **Celery adapter** | L | no (new package) |
| 6 | **`tasks.local_queue` rename** with one-release alias | S | yes (rename) |

Helpers A (`bind_to`) and FastAPI healthcheck routers are listed for
v0.1.0 / v0.1.1 above — they move to v0.2 only if pre-cut review
removes them.

### 6.2 v0.2 task breakdowns

#### v0.2-item-1 — `MetricsSink` cardinality contract

- **Files**: `src/resilience_kit/metrics.py` (Protocol upgrade + new `BoundedMetricsSink` wrapper); `src/resilience_kit/exceptions.py` (new `CardinalityViolation` class); `tests/unit/test_metrics.py` (cardinality enforcement tests); `docs/MIGRATION-from-boilerplate-embedded.md` (new §11 v0.2 upgrade guide); `docs/adr/0012-metrics-cardinality-contract.md` (new ADR).
- **Protocol upgrade**:
  ```python
  class MetricsSink(Protocol):
      # Existing methods stay; one new attribute and one new method:
      cardinality_budget: ClassVar[int]  # default 50 per metric

      def record(
          self,
          *,
          metric: str,
          value: float,
          labels: Mapping[str, str],
          kind: Literal["counter", "gauge", "histogram"],
      ) -> None:
          ...
  ```
- **Implementation notes**:
  - Existing `noop` and `stdlib_logging` sinks gain a class-level `cardinality_budget = 50` default and a tracked `_seen_label_combos: dict[str, set[tuple[str, ...]]]`.
  - When a new label combo for a metric exceeds the budget, raise `CardinalityViolation` (subclass of `ResilienceKitError`). Caller's choice whether to silence (try/except) or block.
  - Ship a `BoundedMetricsSink(inner: MetricsSink, budget: int = 50)` wrapper that any third-party sink can opt into.
  - **Breaking change for third-party `MetricsSink` implementers** — they need to either set `cardinality_budget` or wrap themselves in `BoundedMetricsSink`. Document migration in MIGRATION §11 and the v0.2 release notes.
- **Free-function shim** (lands here, not in v0.1.x):
  ```python
  def record_duration(metric: str, value: float, **labels: str) -> None: ...
  def record_counter(metric: str, value: float = 1.0, **labels: str) -> None: ...
  def record_gauge(metric: str, value: float, **labels: str) -> None: ...
  ```
  Each routes through `get_metrics()` so projects keep their existing call sites.
- **Tests**:
  - `test_record_under_budget_succeeds`.
  - `test_record_over_budget_raises_cardinality_violation`.
  - `test_bounded_metrics_sink_wraps_any_inner_sink`.
  - `test_free_function_shim_routes_to_configured_sink`.
- **Acceptance**: M7 boilerplates can replace their `_assert_bounded` calls with `record_counter(...)` and observe identical cardinality enforcement; ADR documents the breaking-change rationale.
- **Effort**: M-L (~1.5-2 days including ADR + migration doc).
- **Dependencies**: none.

#### v0.2-item-2 — Real `DjangoSettingsSource`

- **Files**: `src/resilience_kit/adapters/django/settings_source.py` (new); `src/resilience_kit/adapters/django/apps.py` (wire into `ResilienceConfig.ready()`); `tests/integration/django_app/test_django_settings_source.py` (new); `docs/adr/0013-django-settings-source.md` (new ADR).
- **Implementation**:
  - `DjangoSettingsSource` implements the `SettingsSource` Protocol; in `load()` it reads `django.conf.settings.RESILIENCE` (whole dict, not just `services`) and feeds it to `ResilienceSettings.model_validate(...)`.
  - With ISSUE-002's `extra="forbid"`, typo'd keys in `RESILIENCE = {...}` raise loud at Django startup — this is the design.
  - `ResilienceConfig.ready()` installs the source via `set_settings_source(DjangoSettingsSource())` unless one is already set (caller can override).
- **Tests**:
  - `test_django_settings_source_reads_whole_resilience_dict` — set `settings.RESILIENCE = {"backend": "memory", "crypto": {"field_encryption_key": "..."}}` and assert `get_settings().crypto.field_encryption_key` matches.
  - `test_django_settings_source_falls_back_to_env_when_dict_missing` — no `settings.RESILIENCE` → kit reads env vars as today.
  - `test_django_settings_source_raises_on_unknown_top_level_key` — proves ISSUE-002 catches typos here too.
- **Acceptance**: Django adopters configure the kit by editing `settings.RESILIENCE`; no env vars needed for non-secret config; ADR documents the precedence (explicit `set_settings_source` → `DjangoSettingsSource` → env).
- **Effort**: M (~1 day including integration test).
- **Dependencies**: PR #15 (`extra="forbid"`) merged.

#### v0.2-item-3 — `GlobalThrottle`

- **Files**: `src/resilience_kit/throttle/global_impl.py` (new); `src/resilience_kit/throttle/lua_scripts.py` (extend with a `global_throttle.lua`); `pyproject.toml` (new entry-point `global = "resilience_kit.throttle.global_impl:GlobalThrottle"` under `resilience_kit.throttle_backends`); `tests/contract/test_throttle_contract.py` (add to parametrize); `tests/integration/test_global_throttle_under_load.py` (new); `docs/adr/0014-global-throttle.md` (new ADR).
- **Implementation**:
  - Implements `AsyncThrottle` Protocol. Single Valkey key per metric (e.g. `rk:throttle:global:request`), sliding-window counter via Lua. Same SHA-cache + NoScriptError reload pattern as the existing Redis throttle.
  - Settings: `RESILIENCE_DEFAULTS__THROTTLE__GLOBAL_RATE="10000/min"`.
  - Contract suite gains a "global" parametrization row; passes the same assertions as `memory` / `redis`.
- **Tests**:
  - Contract suite — `test_throttle_global_blocks_burst_above_rate`.
  - Integration — `test_global_throttle_under_concurrent_load` (testcontainers redis + asyncio.gather).
- **Acceptance**: M7 Django boilerplate can re-enable the system-wide cap by setting `RESILIENCE_DEFAULTS__THROTTLE__BACKEND=global` without losing the boilerplate-local in-process throttle.
- **Effort**: M (~1.5 days including Lua + contract integration).
- **Dependencies**: none.

#### v0.2-item-4 — Flask adapter

- **Files**: new package `src/resilience_kit/adapters/flask/`:
  - `__init__.py` — exports `install_middleware_stack`, `install_exception_handlers`, `install_health_routes`, `rate_limit_decorator`, `register_lifespan`.
  - `lifespan.py` — `register_lifespan(app)` hooks Flask's `before_first_request` + `teardown_appcontext` to start/stop the recovery monitor (Flask has no native ASGI lifespan).
  - `middleware.py` — `install_middleware_stack` wraps each kit ASGI middleware as Flask `before_request` / `after_request` hooks (or mounts via `app.wsgi_app = ...` for the ASGI-native ones via `a2wsgi`).
  - `exception_handlers.py` — `install_exception_handlers(app)` registers Flask `@errorhandler` per kit exception class.
  - `dependencies.py` — `rate_limit_decorator(scope, rate)` since Flask has no DI.
  - `fields.py` — re-exports the SQLAlchemy `EncryptedString` from the FastAPI adapter (same shape).
- **Optional extra**: `[flask]` in `pyproject.toml` pulling `flask>=3.0`.
- **Tests**: `tests/integration/flask_app/` minimal Flask app + httpx test client exercising every public surface.
- **Acceptance**: ROADMAP M5/M6 exit gate adapted for Flask; one adopter outside this repo cuts a Flask app using only kit primitives.
- **Effort**: L (~3-4 days). Largest single item in v0.2.
- **Dependencies**: pattern proven by FastAPI + Django adapters.

#### v0.2-item-5 — Celery adapter

- **Files**: new package `src/resilience_kit/adapters/celery/`:
  - `__init__.py` — exports `task_retry_policy`, `install_recovery_monitor`.
  - `task_retry_policy.py` — `@task_retry_policy(service_name)` decorator that composes with Celery's own retry: uses kit's `retry_on_failure` for transport-layer retries inside the task body, falls through to Celery's `autoretry_for` for orchestration retries.
  - `lifespan.py` — Celery signal hooks (`worker_init`, `worker_shutdown`) that own the recovery monitor in a daemon thread inside the worker process. Mirrors the Django adapter's `ResilienceConfig.ready()`.
- **Optional extra**: `[celery]` pulling `celery>=5.3`.
- **Tests**: `tests/integration/celery_app/` minimal worker + broker (testcontainers redis) exercising retry composition.
- **Acceptance**: a Celery task can be marked `@task_retry_policy("svc")` and gets kit retry + breaker semantics without losing Celery's eager-mode test ergonomics.
- **Effort**: L (~3 days).
- **Dependencies**: none.

#### v0.2-item-6 — `tasks.local_queue` rename

- **Files**: `src/resilience_kit/tasks/__init__.py` (add `local_queue` and `local_registry` as the new canonical names, keep `queue` and `registry` as aliases with `DeprecationWarning` via module-level `__getattr__`); `tests/unit/tasks/test_local_queue_aliases.py` (new).
- **Implementation**: rename the symbols, leave the old names re-exporting via lazy `__getattr__` that warns on first access. Aliases drop in v0.3.
- **Tests**: `test_old_name_warns` + `test_new_name_works_without_warning`.
- **Acceptance**: `from resilience_kit.tasks.local_queue import enqueue` works; `from resilience_kit.tasks.queue import enqueue` works but warns.
- **Effort**: S (~1 hr).
- **Dependencies**: none.

### 6.3 v0.2 exit gate

Both M7 boilerplates re-test against v0.2 on a kit pre-release; their
integration reports score ≥ 8.5/10 (target half a point higher than
0.1.0). Specifically:

- FastAPI report's "would tip the scale further" §1 (`/healthz` routers) is satisfied.
- FastAPI report's §2 (cardinality contract) is satisfied.
- Django report's §4.1 (`DjangoSettingsSource`) is satisfied.
- Django report's §4.3 (`GlobalThrottle`) is satisfied.

---

## 7. v0.3 plan — "operational depth" (target: ~3 months post-0.1.0)

Theme: the ops-team knobs and richer shapes that v0.1 deliberately
narrowed.

### 7.1 Ordered ship plan

| Order | Item | Effort | Breaking? |
|---|---|---|---|
| 1 | **Multi-alias Redis support** — `redis_urls: dict[str, str]` | M | yes (settings schema) |
| 2 | **`HTTPAuditEvent` subclass** for richer HTTP audit | M | no (additive) |
| 3 | **`backend_name` + `reset_backend(alias)`** | S | no (additive) |
| 4 | **`AsyncFernetCipher`** | S | no (additive) |
| 5 | **Shared utility modules** — `resilience_kit.utils.*` | L | no (new namespace) |
| 6 | **Litestar adapter** | L | no (new package) |
| 7 | **`resilience_kit doctor` CLI** | L | no (new tool) |
| 8 | **Drop `AuthType` enum + drop v0.2 alias shims** | S | yes (final removal) |

### 7.2 v0.3 task breakdowns (medium detail)

#### v0.3-item-1 — Multi-alias Redis support

- **Files**: `src/resilience_kit/settings.py` (replace `redis_url: str | None` with `redis_urls: dict[str, str]`, default `{}`); per-subsystem providers (`cache/provider.py`, `throttle/provider.py`, `circuit_breaker/provider.py`, `audit/factory.py`) update to look up `redis_urls.get(alias, redis_urls.get("default"))`; `docs/adr/0015-multi-alias-redis.md` new ADR; `docs/MIGRATION-from-boilerplate-embedded.md` new §12.
- **Breaking change**: `RESILIENCE_REDIS_URL` env var now translates into `RESILIENCE_REDIS_URLS__DEFAULT`. The `legacy_env_alias` table (helper E above) gains this mapping.
- **Acceptance**: same Redis URL for everything still works (no config change required); operators can split via `RESILIENCE_REDIS_URLS__CACHE=redis://...` etc.
- **Tests**: contract suite parametrized over single-URL vs multi-alias config.
- **Effort**: M (~1.5 days).
- **Dependencies**: `legacy_env_alias` (helper E above).

#### v0.3-item-2 — `HTTPAuditEvent` subclass

- **Files**: `src/resilience_kit/audit/events.py` (new `HTTPAuditEvent(AuditEvent)` dataclass); `src/resilience_kit/audit/decorators.py` (`@log_inbound_http` and `@log_outbound_http` decorators that produce `HTTPAuditEvent` instead of `AuditEvent`); `tests/unit/audit/test_http_audit_event.py` new.
- **Shape**: `HTTPAuditEvent` adds `request_headers: dict[str, str]`, `request_body_redacted: str | None`, `response_status: int | None`, `response_headers: dict[str, str]`, `response_body_redacted: str | None`, `ttl_expires_at: datetime | None`, `environment: str`.
- **Backends**: `PostgresAuditBackend` checks `isinstance(event, HTTPAuditEvent)` and serializes the extra columns into a separate `http_audit_events` table; `StdlibLoggingAuditBackend` just dumps the dict.
- **Acceptance**: M7 boilerplates can replace their hand-rolled `ApiLog` ORM pipeline with kit's `HTTPAuditEvent` + custom backend.
- **Effort**: M (~2 days).
- **Dependencies**: none.

#### v0.3-item-3 — `backend_name` + `reset_backend(alias)`

- **Files**: `src/resilience_kit/recovery.py` (new `reset_provider(alias: str)` + `registered_backends()` introspection); `src/resilience_kit/adapters/django/management/commands/resilience_reset.py` (extend to take `--backend redis` flag); `src/resilience_kit/adapters/django/management/commands/resilience_status.py` (extend output with `backend_name`).
- **Tests**: `test_reset_provider_resets_only_named_alias` (other backends unaffected).
- **Acceptance**: operator can `./manage.py resilience_reset --backend redis` to force-recover one alias without touching others.
- **Effort**: S (~3 hr).
- **Dependencies**: none.

#### v0.3-item-4 — `AsyncFernetCipher`

- **Files**: `src/resilience_kit/crypto/fernet.py` (new `AsyncFernetCipher` class mirroring sync surface); `tests/unit/crypto/test_async_fernet.py` new.
- **Implementation**: `async def encrypt(...)` / `async def decrypt(...)` wrap the sync calls in `asyncio.to_thread` internally — caller no longer has to.
- **Acceptance**: import works behind `[crypto]` extra; identical round-trip semantics; no key-cache duplication (shares `lru_cache` with sync class).
- **Effort**: S (~2 hr).
- **Dependencies**: none.

#### v0.3-item-5 — Shared utility modules

- **Files**: new `src/resilience_kit/utils/` package with submodules:
  - `log_sanitization.py` — generic deep-walk redactor (mirrors boilerplate's pattern; superset of `audit.sanitizers.DefaultRedactor`).
  - `network.py` — `client_ip_from_headers(headers, trusted_hops=1)` + IPv4/IPv6 helpers.
  - `timing.py` — `monotonic_ms()`, `Stopwatch` context manager, `human_duration(seconds)`.
  - `function_logger.py` — `@log_function(name=None, redact_args=...)` decorator.
  - `data.py` — `chunked(iterable, size)`, `deep_merge(a, b)`, `frozen_dict(...)` immutable mapping helper.
- **Tests**: one `tests/unit/utils/test_<module>.py` per submodule.
- **Acceptance**: M7 boilerplates can replace their `core/utils/*.py` versions with `from resilience_kit.utils import ...` and remove ~900 LOC each.
- **Effort**: L (~3-4 days for all five with tests).
- **Dependencies**: none.

#### v0.3-item-6 — Litestar adapter

- **Files**: new `src/resilience_kit/adapters/litestar/` package mirroring `adapters/fastapi/` structure.
- **Optional extra**: `[litestar]` pulling `litestar>=2.0`.
- **Tests**: `tests/integration/litestar_app/` minimal Litestar app exercising every surface.
- **Acceptance**: adapter parity with `adapters/fastapi`.
- **Effort**: L (~2-3 days, smaller than Flask because Litestar's API is closer to FastAPI's).
- **Dependencies**: none.

#### v0.3-item-7 — `resilience_kit doctor` CLI

- **Files**: new `src/resilience_kit/cli/doctor.py`; `pyproject.toml` adds `[project.scripts]` `resilience-kit-doctor = "resilience_kit.cli.doctor:main"`.
- **Checks**:
  - **Unprotected outbound calls**: AST scan for `httpx.get/post/...` and `requests.get/post/...` not inside a function decorated with `@resilient` / `@retry`. Severity: warning.
  - **Unbounded metric labels**: AST scan for `record_*` calls with non-literal label values (e.g. `record_counter(...)` with `**request.headers`). Severity: error.
  - **Legacy env-var names**: scan `.env*` files for keys in the `legacy_env_alias` table. Severity: warning.
  - **Missing `bind_to`**: if the project imports `from resilience_kit.context import request_id` and also defines its own `request_id_ctx: ContextVar`, suggest `bind_to(request_id_ctx)`. Severity: info.
- **Output**: tabular + JSON modes; non-zero exit on errors.
- **Tests**: `tests/unit/cli/test_doctor.py` with synthetic project trees as fixtures.
- **Acceptance**: a fresh M7-migrated boilerplate runs cleanly; an intentionally bad project trips each check.
- **Effort**: L (~2-3 days).
- **Dependencies**: utility modules (item 5) for the AST helpers.

#### v0.3-item-8 — Drop deprecation shims

- **Files**: `src/resilience_kit/http_client/auth.py` (delete `__getattr__` for `AuthType`); `src/resilience_kit/tasks/queue.py` + `tasks/registry.py` (delete the alias shims from v0.2-item-6); CHANGELOG breaking-change entry.
- **Acceptance**: v0.2 deprecation warnings are gone; old imports raise `ImportError`.
- **Effort**: S (~30 min).
- **Dependencies**: v0.2-item-6 shipped its alias one release prior.

### 7.3 v0.3 exit gate

A third-party adopter (any project outside the two M7 boilerplates)
deploys v0.3 to production without filing a regression issue.

---

## 8. v0.4 plan — "visibility" (no fixed target)

- **Sphinx + `mkdocs-material` docs site** under `resilience-kit.dev` (or GitHub Pages). Replaces `docs/` markdown as the canonical reference; markdown stays for in-repo greppability.

Lands when one of two triggers fires:

- The project has ≥ 3 third-party adopters and the markdown tree stops scaling, or
- A blog post or talk wants a hosted reference URL.

---

## 9. Maintenance lines (always on)

Not tied to any version slot.

- **Dependabot** — weekly across GH Actions + Python deps; security patches merge same-day.
- **CHANGELOG `[Unreleased]`** — one-line entry per user-visible change, no exceptions. `release.yml` extracts the matching section as release notes.
- **Boilerplate dogfooding pin** — kit + both boilerplates re-test integration on every kit minor (`v0.2.0`, `v0.3.0`, …) *before* the kit tag pushes. Integration reports diffed against the prior cycle's; regressions block the cut.
- **Security advisories** — privately reported via [GitHub Security Advisories](https://github.com/prajwalmahajan101/resilience-kit/security/advisories/new), first response within 5 business days. See [SECURITY.md](../SECURITY.md).

---

## 10. Risk register

Things to watch that could derail or delay v0.1.0 or the post-0.1.0
plan.

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | PyPI Trusted Publisher config incorrect → first `release.yml` run fails on `publish-pypi` | medium | high (delays cut) | Dry-run by tagging a `v0.1.0rc2` first; verify each job before tagging `v0.1.0` proper. |
| R2 | Pre-existing darglint / mypy noise blocks CI on the docs PRs | low | medium | Already noted in PR bodies; main itself fails the same way. Fix in a separate cleanup PR if it starts breaking new work. |
| R3 | M7 boilerplate PRs reveal a v0.1.0 blocker not yet captured | low | high | Both M7 reports are in; no new blockers. If one surfaces during their final merge review, file as `feat/m8b-issue-XXX` branch and merge before the cut. |
| R4 | `MetricsSink` cardinality contract design takes longer than the v0.2 window | medium | medium | Treat v0.2 as a target, not a deadline. If the design needs more iteration, push to v0.3 and ship the other v0.2 items first. |
| R5 | `extra="forbid"` (PR #15) breaks an existing adopter who pinned a typo'd env-var | low | medium | The whole point of the change. Mitigate by calling it out loudly in v0.1.0 release notes (CHANGELOG entry already drafted). |
| R6 | Pre-cut helpers (§3.1) introduce regressions because they go in without external review | medium | low | Each helper is independently revertible; CI catches obvious breaks; the helpers are designed to be additive, so worst case is dead code. |

---

## 11. Decision log

Record `RELEASE-PLAN.md`-level decisions here when they're made so the
context survives the conversation.

| Date | Decision | Source |
|---|---|---|
| 2026-06-10 | Bundle M8b doc work into one PR (`feat/m8b-docs`) instead of four | User accepted §C plan in conversation |
| 2026-06-10 | Defer `MIGRATION.md` updates until both dogfooding reports arrive | User direction |
| 2026-06-10 | Ship `release.yml` with PyPI Trusted Publishing (no API token in secrets) | Section D of M8b brief |
| 2026-06-10 | Refresh ROADMAP "Beyond v0.1" with dogfooding-derived version slots | User: "for all the defer add the version plan feature documentation" |
| 2026-06-10 | Plan and document the pre-cut helpers + v0.1.x / v0.2 / v0.3 tasks (this doc); **do not execute** | User: "dont do anythong now plan for it and document all the changes that are need and the task that we to complete also the plan what will go in which release" |
| 2026-06-11 | Approved §3.1 pre-cut helpers A–E in v0.1.0 (full bundle, additive only) | User: "we have D1 ... If approved → open feat/m8b-pre-cut-ergonomics and execute." |
| 2026-06-11 | Landed `feat/m8b-pre-cut-ergonomics` — `bind_to`, `reset_all_singletons_async`, `verify_envelope_contract`, `from_exception` (+adapter refactor), `legacy_env_alias` | This branch / commits e877a88..3b3238d (PR #22 merged at 2cc554c) |
| 2026-06-11 | Wrote rc1→v0.1.0 upgrade doc + standardized migration report template | [`docs/MIGRATION-rc1-to-v0.1.0.md`](./MIGRATION-rc1-to-v0.1.0.md) — sink for adopter feedback into v0.1.x / v0.2 ROADMAP |
| 2026-06-11 | Cut v0.1.0 + published to PyPI via Trusted Publishing (after release.yml smoke-assertion fix in PR #24) | `main@db96edb` tagged `v0.1.0`; PyPI shows 0.1.0 non-pre-release; GitHub Release `v0.1.0` (`isPrerelease=false`) with sdist + wheel attached |
| 2026-06-11 | Intook M8b boilerplate upgrade reports — FastAPI 8/10, Django 9/10 (both ≥ 8/10 clean-cut gate) | [`docs/m8b-upgrade-reports/`](./m8b-upgrade-reports/) — reports verbatim + `SUMMARY.md` synthesis; six v0.1.1 patch-line candidates and four doc-gap fixes folded into `MIGRATION-rc1-to-v0.1.0.md` + `ROADMAP.md` |

---

## 12. Quick reference — what goes where

Pasted-friendly index of every planned change by release. Each entry
links to its task-breakdown subsection.

### Inside v0.1.0 (pre-cut bundle, awaiting approval)

| Item | Section | Status |
|---|---|---|
| Helper A — `bind_to(consumer_ctxvar)` | §3.2 | planned, not started |
| Helper B — `reset_all_singletons_async()` | §3.2 | planned, not started |
| Helper C — `verify_envelope_contract()` | §3.2 | planned, not started |
| Helper D — `from_exception(exc, envelope_cls=)` | §3.2 | planned, not started |
| Helper E — `legacy_env_alias()` | §3.2 | planned, not started |

### v0.1.0 already in-flight (PRs #15-#20, #21)

| Item | PR | Status |
|---|---|---|
| ISSUE-002 `extra="forbid"` | #15 | merge-ready |
| Docs bundle (SECURITY/CONTRIBUTING/ADRs/README) | #17 | merge-ready |
| ISSUE-003/004/005 follow-ups | #18 | merge-ready |
| `release.yml` Trusted Publishing | #16 | merge-ready |
| ROADMAP v0.2+ planning | #19 | merge-ready |
| MIGRATION post-dogfooding patterns + adapter docstrings | #20 | merge-ready |
| This release plan | #21 | merge-ready |

### v0.1.x patch line

| Item | Section | Target |
|---|---|---|
| FastAPI healthcheck routers | §5.2 | v0.1.1 |
| `AuthType` deprecation shim *(conditional)* | §5.2 | v0.1.2 |

### v0.2

| Item | Section | Breaking? |
|---|---|---|
| `MetricsSink` cardinality contract + free-function shim | §6.2 v0.2-item-1 | yes |
| Real `DjangoSettingsSource` | §6.2 v0.2-item-2 | no |
| `GlobalThrottle` Valkey-Lua | §6.2 v0.2-item-3 | no |
| Flask adapter | §6.2 v0.2-item-4 | no |
| Celery adapter | §6.2 v0.2-item-5 | no |
| `tasks.local_queue` rename | §6.2 v0.2-item-6 | yes |

### v0.3

| Item | Section | Breaking? |
|---|---|---|
| Multi-alias Redis | §7.2 v0.3-item-1 | yes |
| `HTTPAuditEvent` subclass | §7.2 v0.3-item-2 | no |
| `backend_name` + `reset_backend(alias)` | §7.2 v0.3-item-3 | no |
| `AsyncFernetCipher` | §7.2 v0.3-item-4 | no |
| Shared utility modules | §7.2 v0.3-item-5 | no |
| Litestar adapter | §7.2 v0.3-item-6 | no |
| `resilience_kit doctor` CLI | §7.2 v0.3-item-7 | no |
| Drop v0.2 alias shims | §7.2 v0.3-item-8 | yes |

### v0.4

| Item | Section |
|---|---|
| Sphinx + mkdocs-material site | §8 |
