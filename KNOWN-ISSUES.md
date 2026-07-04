# Known Issues — `resilience-kit`

> Live catalog of the **open** issues from the four-lens audit (`audit/RKIT-L{1,2,3,4}-*.md`).
> Closed issues are removed once shipped — their full history lives in `CHANGELOG.md`,
> the ADRs, and git. As of **v0.2.0** only the Lane D deferrals remain open.
>
> **Status legend:** `open` · `in-progress` · `fixed` (removed on release) · `wontfix` · `deferred`
>
> **GH column:** GitHub issue number when filed. Empty = not yet on the tracker.
>
> Update protocol: any PR that changes status here must touch this file in the same commit.

---

## Resolved in v0.2.0

**29 of the original 35 audit issues are fixed and shipped in v0.2.0** — all of
Lane A (#A1–#A14, quick-wins + CI gates), Lane B (#B1–#B8, correctness/security),
Lane C (#C1–#C6, observability + crypto rotation + ASGI), and the Lane D hardening
subset (#D1 shared Redis client, #D2 sync-breaker loop-rebind, #D4 Hypothesis
property tests, #D5 SBOM, #D6 signed releases). See [`CHANGELOG.md`](./CHANGELOG.md)
`[0.2.0]` and ADRs 0012–0017 for the detail; git history is bisectable per issue.

The **6 remaining open issues** below are the Lane D deferrals: two need a person
or external action (#D3, #D11), four are new ecosystem surfaces (#D7–#D10).

---

## Severity legend

| Tag | Meaning |
|---|---|
| 🔴 **CRITICAL** | Active security or correctness vulnerability with realistic exploit path. |
| 🟠 **HIGH** | Correctness bug, locked-API drift, or reliability gap that bites under production load. |
| 🟡 **MEDIUM** | Hygiene, code-quality, or doc-fidelity gap. |
| 🟢 **LOW** | Quick wins, OSS hygiene, classifier corrections. |
| 🔵 **ECOSYSTEM** | New surfaces (Flask/Celery adapters, CLI, docs site). |

---

## Index

- [#D3 — Bus-factor 1: name a co-maintainer](#d3--bus-factor-1--name-a-co-maintainer)
- [#D7 — Flask adapter](#d7--add-flask-adapter)
- [#D8 — Celery adapter](#d8--add-celery-adapter)
- [#D9 — `resilience-kit doctor` CLI](#d9--add-resilience-kit-doctor-cli)
- [#D10 — Hosted documentation site](#d10--hosted-documentation-site-sphinx-or-mkdocs)
- [#D11 — Announcement post + adoption signal](#d11--announcement-post--adoption-signal)

**v0.3.0 quality + adapters lane** (planned):

- [#D12 — Chaos / fault-injection test suite](#d12--chaos--fault-injection-test-suite)
- [#D13 — Load / throughput benchmarks](#d13--load--throughput-benchmarks)
- [#D14 — Raise coverage floor with a Redis-backed CI job](#d14--raise-coverage-floor-with-a-redis-backed-ci-job)
- [#D15 — Native Django sync + async adapters](#d15--native-django-sync--async-adapters)
- [#D16 — Flask + FastAPI adapters: sync/async parity](#d16--flask--fastapi-adapters-syncasync-parity)

---

### #D3 🟠 Bus-factor 1 — name a co-maintainer

**Severity:** HIGH · **Impact:** 5 · **Effort:** 4 · **Priority:** 1.25 · **GH:** _unfiled_ · **Status:** `deferred` → v0.3.0 (needs a real co-maintainer + repo-admin grant; not a code change)

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

### #D7 🔵 Add Flask adapter

**Severity:** ECOSYSTEM · **Impact:** 4 · **Effort:** 5 · **Priority:** 0.80 · **GH:** _unfiled_ · **Status:** `open`

**Where:** New `src/resilience_kit/adapters/flask/`; new `src/resilience_kit/middleware/wsgi/`

**Problem.** Kit ships ASGI middleware only. Flask is WSGI. ROADMAP M9 noted "WSGI mirrors land alongside Flask adapter" — never delivered.

**Fix.** ~150 LOC of WSGI middleware (mirroring six ASGI classes) + ~100 LOC of Flask adapter (lifecycle wrapper via `before_first_request`/`teardown_appcontext`, `errorhandler` bridge, blueprint with `/healthz`/`/readyz`).

**Acceptance.** A Flask app installs `resilience-kit[flask]`, wires `init_resilience(app)`, and gets `/healthz`/`/readyz` + request-id middleware + rate-limit headers.

---

### #D8 🔵 Add Celery adapter

**Severity:** ECOSYSTEM · **Impact:** 3 · **Effort:** 4 · **Priority:** 0.75 · **GH:** _unfiled_ · **Status:** `open`

**Where:** New `src/resilience_kit/adapters/celery/`

**Problem.** No native Celery integration. `@retry` + `@circuit_breaker` work on Celery tasks but the task lifecycle (signals, soft-timeout, task-id propagation) isn't wired into the kit's ContextVar discipline.

**Fix.** Adapter that:
1. Propagates `request_id` from caller into task headers, restores on task entry.
2. Wires `task_failure` / `task_retry` signals into the kit's audit dispatcher.
3. Provides `@resilient_task` decorator combining `@app.task` + `@resilient(name)`.

**Acceptance.** A Celery task decorated `@resilient_task("downstream-api")` propagates request-id and emits audit events on failure.

---

### #D9 🔵 Add `resilience-kit doctor` CLI

**Severity:** ECOSYSTEM · **Impact:** 3 · **Effort:** 5 · **Priority:** 0.60 · **GH:** _unfiled_ · **Status:** `open`

**Where:** New `src/resilience_kit/cli/`; `pyproject.toml` `[project.scripts]`

**Problem.** Operators landing on the kit have no quick health-check. A `doctor` CLI that validates settings, probes Redis/Postgres connectivity, lists discovered backends, and dumps the effective config would dramatically reduce onboarding friction.

**Fix.** Click/Typer-based CLI:
- `resilience-kit doctor` — full health probe.
- `resilience-kit list-backends` — show resolved backends per subsystem.
- `resilience-kit settings` — dump effective config (redacted).
- `resilience-kit migrate-key --from=<sha256-key> --to=<fernet-key>` — key rotation (builds on the shipped #C1 `MultiFernet` support).

**Acceptance.** `resilience-kit doctor` exits 0 on a correctly-configured dev environment and exits 1 with actionable diagnostics on a misconfigured one.

---

### #D10 🔵 Hosted documentation site (Sphinx or MkDocs)

**Severity:** ECOSYSTEM · **Impact:** 3 · **Effort:** 4 · **Priority:** 0.75 · **GH:** _unfiled_ · **Status:** `open`

**Where:** New `docs/` site config; GitHub Pages workflow

**Problem.** `py.typed` + mypy-strict-clean codebase begs for auto-generated API reference. ROADMAP v0.4 parks "Sphinx + mkdocs-material."

**Fix.** MkDocs-material with `mkdocstrings[python]` for auto-API. Configure GitHub Pages publish via existing release.yml hook. Use existing `docs/*.md` as the navigation tree.

**Acceptance.** `https://prajwalmahajan101.github.io/resilience-kit/` (or custom domain) serves rendered docs.

---

### #D11 🔵 Announcement post + adoption signal

**Severity:** ECOSYSTEM · **Impact:** 4 · **Effort:** 2 · **Priority:** 2.00 · **GH:** _unfiled_ · **Status:** `deferred` → v0.3.0 (external publishing + adoption signal; not a code change)

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

## v0.3.0 quality + adapters lane

Requested for the next minor: deeper testing (chaos + load) and first-class
sync/async parity across every adapter. Scoped here so they carry acceptance
criteria before a branch opens.

### #D12 🟡 Chaos / fault-injection test suite

**Severity:** MEDIUM · **Impact:** 4 · **Effort:** 4 · **Priority:** 1.00 · **GH:** _unfiled_ · **Status:** `open` → v0.3.0

**Where:** New `tests/chaos/`

**Problem.** The kit's headline promise is graceful degradation (fail-open cache/breaker/throttle, recovery re-probe, audit fire-and-forget). Today that path is covered by unit stubs (`_DeadRedis`) and a few integration tests — never under *sustained, randomised* fault injection: mid-flight Redis kills, latency spikes, connection resets, Postgres pool exhaustion, partial Lua failures, clock skew during a Sentinel failover.

**Fix.** A `tests/chaos/` suite (testcontainers + a fault-injection proxy such as Toxiproxy, or `pumba` against the Redis/Postgres containers) that asserts the kit's invariants hold while the backend is actively degrading: no dropped recovery, no duplicate pools (#D1), no double-count on the breaker, throttle fail-mode honoured, audit drain bounded. Run as a separate, non-blocking-then-required CI lane.

**Acceptance.** A chaos scenario that kills + revives Redis 20× under load leaves every primitive in a correct state and the recovery monitor converges; the suite is green in CI.

---

### #D13 🟡 Load / throughput benchmarks

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 3 · **Priority:** 1.00 · **GH:** _unfiled_ · **Status:** `open` → v0.3.0

**Where:** New `benchmarks/` + a `bench` CI job

**Problem.** No published throughput/latency numbers for the decorators, the throttle Lua round-trip, or the middleware stack. The global CLAUDE.md performance budget (p95 < 200 ms user-facing) is asserted nowhere and can regress silently.

**Fix.** `pytest-benchmark` micro-benchmarks for `@resilient`, breaker `call`, throttle `check` (memory + Redis), and an end-to-end adapter benchmark under concurrency (`locust` or `k6` against a sample FastAPI/Django app). Track results over time (e.g. `github-action-benchmark`) and alert on regression past a threshold.

**Acceptance.** A `bench` job publishes p50/p95/p99 for the core primitives and fails on a >X% regression vs the baseline committed in `benchmarks/baseline.json`.

---

### #D14 🟡 Raise coverage floor with a Redis-backed CI job

**Severity:** MEDIUM · **Impact:** 3 · **Effort:** 2 · **Priority:** 1.50 · **GH:** _unfiled_ · **Status:** `open` → v0.3.0

**Where:** `.github/workflows/ci.yml`; `pyproject.toml` `[tool.coverage]`

**Problem.** The `--cov-fail-under` floor is **68** (set in #A7), not 85, because the gated unit job runs without Redis so the Redis backends (~30% of the code) are uncovered there. The Redis paths *are* exercised in `integration.yml`, but that coverage isn't merged into the gate.

**Fix.** Add a Redis/Postgres-service coverage job (or fold the integration run's `coverage.xml` into a combined report via `coverage combine`), then raise the floor toward 85. Follow-up to #A7's own note.

**Acceptance.** Combined coverage across unit + integration is measured in CI and the `--cov-fail-under` floor is raised to ≥85 without excluding the Redis backends.

---

### #D15 🟠 Native Django sync + async adapters

**Severity:** HIGH · **Impact:** 4 · **Effort:** 4 · **Priority:** 1.00 · **GH:** _unfiled_ · **Status:** `open` → v0.3.0

**Where:** `src/resilience_kit/adapters/django/`; ADR-0011

**Problem.** Under ASGI Django the kit's middleware is sync-capable only — Django wraps it via `sync_to_async` (the dead `__acall__` methods were removed in #A2, deferring native async to here). Every request pays a thread-pool hop. The DRF throttle now bridges onto the daemon loop (#C6) but the middleware stack and audit path do not have a native async branch.

**Fix.** Implement the documented Django async-middleware recipe (`__call__` returning an awaitable + `sync_and_async_capable` marker / `markcoroutinefunction`) so ASGI deployments run the kit natively async, WSGI stays sync, and neither pays the wrapper tax. Amend ADR-0011 with the resolution and add an ASGI integration test that asserts the async path is exercised (no `sync_to_async` on the hot path).

**Acceptance.** An ASGI Django integration test shows the kit middleware runs on the event loop without a `sync_to_async` hop; the WSGI path is unchanged.

---

### #D16 🟠 Flask + FastAPI adapters: sync/async parity

**Severity:** HIGH · **Impact:** 4 · **Effort:** 4 · **Priority:** 1.00 · **GH:** _unfiled_ · **Status:** `open` → v0.3.0 (depends on #D7)

**Where:** `src/resilience_kit/adapters/fastapi/`; new `src/resilience_kit/adapters/flask/`; `src/resilience_kit/middleware/wsgi/`

**Problem.** FastAPI (ASGI) is async-native but its sync-endpoint story (a FastAPI `def` route) isn't documented or tested against the kit primitives. Flask (WSGI) has no adapter at all (#D7). There is no shared story for "same resilience primitives, both concurrency models."

**Fix.** Land the Flask/WSGI adapter (#D7) *and* give both adapters an explicit, tested sync **and** async surface: FastAPI sync-route bridging + the existing async path; Flask sync path + an async-view path for `flask[async]`. Share one WSGI middleware mirror of the six ASGI classes. Document the matrix (framework × sync/async) with a working example each.

**Acceptance.** A 2×2 matrix test (FastAPI/Flask × sync/async) shows request-id middleware, rate-limit headers, and `/healthz`/`/readyz` working in all four combinations.

---

## Snapshot table — open issues

| ID | Severity | Title | Impact | Effort | Priority | Lane | GH | Status |
|---|:---:|---|:---:|:---:|:---:|:---:|---|---|
| #D3 | 🟠 | Bus factor — co-maintainer | 5 | 4 | 1.25 | D | _-_ | deferred → v0.3.0 |
| #D7 | 🔵 | Flask adapter | 4 | 5 | 0.80 | D | _-_ | open |
| #D8 | 🔵 | Celery adapter | 3 | 4 | 0.75 | D | _-_ | open |
| #D9 | 🔵 | doctor CLI | 3 | 5 | 0.60 | D | _-_ | open |
| #D10 | 🔵 | Hosted docs site | 3 | 4 | 0.75 | D | _-_ | open |
| #D11 | 🔵 | Announcement post | 4 | 2 | 2.00 | D | _-_ | deferred → v0.3.0 |
| #D12 | 🟡 | Chaos / fault-injection suite | 4 | 4 | 1.00 | v0.3 | _-_ | open |
| #D13 | 🟡 | Load / throughput benchmarks | 3 | 3 | 1.00 | v0.3 | _-_ | open |
| #D14 | 🟡 | Coverage floor → 85 (Redis CI) | 3 | 2 | 1.50 | v0.3 | _-_ | open |
| #D15 | 🟠 | Native Django sync+async adapters | 4 | 4 | 1.00 | v0.3 | _-_ | open |
| #D16 | 🟠 | Flask+FastAPI sync/async parity | 4 | 4 | 1.00 | v0.3 | _-_ | open |

---

## How to use this file

1. **Triage:** #D11 (announcement, priority 2.00) and #D3 (co-maintainer) carry the
   highest priority of the remainder but need *your* action, not code. The four
   🔵 ecosystem surfaces (#D7–#D10) are the next code milestones.
2. **File on GitHub:** open issues for the ones you intend to schedule; backfill the
   `GH:` column with `#NN`.
3. **Update status on close:** the PR that fixes an issue removes its section here
   (and its snapshot row) in the same commit, and records it under the matching
   `CHANGELOG.md` version.

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

Last updated: 2026-07-04 (v0.2.0 — closed issues removed; see CHANGELOG for history).
