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

### 3.1 ✅ Recommend landing pre-0.1.0

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
- [ ] Open follow-up PRs in both boilerplates to re-pin from `==0.1.0rc1` → `==0.1.0`.

---

## 5. v0.1.x patch line (post-0.1.0, additive only)

Items that didn't make the pre-cut bar in §3.1 land here, one or two
per minor version, no breaking changes. Cut whenever there's a reason
to (a security advisory, a downstream blocker, accumulated polish).
See [ROADMAP.md](./ROADMAP.md#v01x-patch-line--additive-non-breaking)
for the canonical list.

Order of expected ship (subject to adopter demand):

1. **`AuthType` deprecation shim** (if any caller still uses the enum)
2. **FastAPI healthcheck routers** (most-requested by FastAPI adopters)
3. **Free-function metrics shim** *(may move to v0.2 instead — depends on whether the cardinality contract lands as v0.2 or v0.1.x)*

---

## 6. v0.2 plan — "adopter ergonomics" (target: ~6 weeks post-0.1.0)

Theme: close the three biggest *needed-this-in-production* gaps the
FastAPI dogfooding flagged, plus the two new framework adapters that
were on the original v0.1 punt list.

Ordered by impact:

1. **FastAPI healthcheck routers** in `adapters/fastapi` (if not landed in v0.1.x).
2. **`MetricsSink` cardinality contract** + free-function shim (`record_duration`, `record_counter`, `record_gauge`). **Breaking inside v0.2** — needs a one-paragraph migration note.
3. **Real `DjangoSettingsSource`** that makes `settings.RESILIENCE = {...}` load-bearing for the full kit schema, not just `services`. Highest-leverage Django dogfooding ask.
4. **`bind_to(consumer_ctxvar)` helper** (if not landed in v0.1.x).
5. **`GlobalThrottle`** — Valkey-Lua system-wide cap.
6. **Flask adapter** — same shape as `adapters/fastapi`.
7. **Celery adapter** — `@task_retry_policy(...)` + lifespan for the recovery monitor inside a Celery worker.
8. **`tasks.local_queue` rename** with one-release alias.

Exit gate: both M7 boilerplates re-test against v0.2 on a kit
pre-release; their integration reports score ≥ 8.5/10 (target half a
point higher than 0.1.0).

---

## 7. v0.3 plan — "operational depth" (target: ~3 months post-0.1.0)

Theme: the ops-team knobs and richer shapes that v0.1 deliberately
narrowed.

1. **Multi-alias Redis support** — `redis_urls: dict[str, str]`.
2. **Shared utility modules** — `resilience_kit.utils.{log_sanitization, network, timing, function_logger, data}`.
3. **`HTTPAuditEvent` subclass** with separate `request_headers` / `request_body` / `response_status` / `ttl_expires_at` / `environment` columns.
4. **`AsyncFernetCipher`** — async surface mirroring the sync class.
5. **`backend_name` + `reset_backend(alias)`** surgical-reset API.
6. **Litestar adapter** — same surface as `adapters/fastapi`.
7. **`resilience_kit doctor` CLI** — static-analysis scanner for unprotected outbound calls, unbounded metric labels, and legacy env-var names.

Exit gate: third-party adopter (any project outside the two boilerplates)
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
| TBD | Land §3.1 pre-cut helpers (A-E) before v0.1.0 cut? | Awaiting decision |
