# Contributing to `resilience-kit`

This is a small portfolio library — issues and PRs are welcome but I am the
only maintainer. The contract test suite under `tests/contract/` is the
source of truth: any new backend must pass it, parametrized in.

## Quick start

```bash
git clone https://github.com/prajwalmahajan101/resilience-kit
cd resilience-kit
uv sync --all-extras --dev
uv run pre-commit install            # optional — wires hooks into git
uv run pytest tests/unit tests/contract -q
```

`uv` ≥ 0.4 and Python ≥ 3.11 are required. The dev interpreter pinned in
`.python-version` is 3.12.

## The full local gate (CI runs the same thing)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src
uv run lint-imports                  # enforces L0–L4 layering (LLD §1)
uv run pytest tests/unit -q
uv run pytest tests/contract -q      # parametrized over all backends
uv run pytest tests/integration -q   # needs Docker — testcontainers
uv run pre-commit run --all-files
```

Pre-commit covers ruff (lint + format), `mypy --strict src`, pydocstyle
(Google convention), darglint, YAML/TOML checks, import-linter (pre-push
stage), and a manual `verify-extras-matrix` hook that installs each extra
in a clean venv to confirm declared deps are sufficient.

Three GitHub Actions workflows gate every PR:

| Workflow | Gates |
|---|---|
| `ci.yml` | lint · types · import layers · unit + contract on Python 3.11/3.12/3.13 |
| `integration.yml` | contract + integration suites against `redis:7` and `valkey:8` |
| `codeql.yml` | CodeQL security + quality scan (weekly + per-PR) |

## Branch + commit policy

- **Milestones** (M0–M8 in [docs/ROADMAP.md](./docs/ROADMAP.md)) ship on
  `feat/m<N>-<slug>` branches. Never push milestone code to `main`.
- **Docs / chore** (README tweaks, ADRs, typo fixes, dep bumps) may land
  directly on `main`.
- **Conventional Commits**, with scopes matching `src/resilience_kit/`
  subpackages — `retry`, `breaker`, `throttle`, `cache`, `ssrf`,
  `http_client`, `crypto`, `audit`, `middleware`, `registry`, `recovery`,
  `adapters/django`, `adapters/fastapi`. Examples:
  - `feat(m<N>): …` for milestone-level work
  - `feat(<module>): …`, `fix(<module>): …`, `refactor(<module>): …`
  - `docs: …`, `test: …`, `chore: …`, `build: …`, `ci: …`
- Subject ≤ 72 chars, no trailing period.
- **No AI attribution footer** — no `Co-Authored-By: Claude` line.
- Squash-merge milestones to `main`; tag the merge commit `milestone/m<N>`
  for bisectability.

## Architectural conventions

- **Protocols, not ABCs.** Every swappable subsystem is `typing.Protocol`.
  See [ADR 0001](./docs/adr/0001-protocol-not-abc.md).
- **Single package, many extras.** No micro-packages. See
  [ADR 0003](./docs/adr/0003-single-package-with-extras.md).
- **Hand-rolled retry, no `tenacity`.** See
  [ADR 0002](./docs/adr/0002-handrolled-retry-not-tenacity.md).
- **Outer breaker, inner retry.** Composition order is locked. See
  [ADR 0006](./docs/adr/0006-outer-breaker-inner-retry.md).
- **Async-first.** Sync wrappers exist where the primitive is idiomatically
  sync; never the other way around.
- **Fail-open on resilience-infra failure.** A dead Valkey must not block
  all requests — degrade to in-memory and let the recovery monitor restore
  the backend.
- **ContextVars are the cross-cutting bus.** `request_id`, `correlation_id`,
  `pinned_dns` — never threading locals, never globals.
- **Adapters have zero business logic.** They wire kit primitives into
  framework lifecycles. If an adapter file grows past ~300 LOC, the
  primitive is wrong, not the adapter.

## When to write an ADR

Add a numbered file under `docs/adr/` (Context / Decision / Consequences /
Usage, matching `0005-fire-and-forget-audit.md`) when you:

- Introduce a new protocol or swappable subsystem.
- Change the composition order of decorators or middleware.
- Adopt or drop a runtime dependency.
- Pick between alternatives that "future you" will ask *why did we choose
  this?* about.

ADRs are cheap. Err on the side of writing one.

## Adding a backend

A third-party backend (cache, breaker, throttle, audit sink, audit
sanitizer, metrics sink) needs **three** things:

1. **Implement the Protocol** in your own package. Structural typing — no
   inheritance from the kit. See e.g. `resilience_kit.cache.base.AsyncCache`.

2. **Declare an entry point** in your `pyproject.toml`, in the matching
   group (see [ADR 0004](./docs/adr/0004-entry-points-for-third-party-backends.md)):

   ```toml
   [project.entry-points."resilience_kit.cache_backends"]
   memcached = "rk_memcached:MemcachedCache"
   ```

3. **Pass the contract suite** parametrized over your backend. Copy the
   pattern in `tests/contract/conftest.py` — the `breaker_factory`,
   `throttle_factory`, and `cache_factory` fixtures take a `params=[...]`
   list of backend names and pytest auto-runs each test once per backend.
   The kit's own builtins plus a fake third-party fixture
   (`tests/fixtures/fake_third_party/`) exercise the resolver chain in CI.

Resolution order in `src/resilience_kit/_providers.py`: explicit callable
→ importable string → entry point → builtin → `UnknownBackendError` with
the list of available names. Third-party entry points shadow same-named
builtins by design (drop-in replacement); namespace your backend names to
avoid accidental collisions.

## Pull requests

- Open against `main`. PR title is the Conventional Commit subject the
  squash will use.
- PR body must quote the milestone's *"Exit when"* line from
  [docs/ROADMAP.md](./docs/ROADMAP.md) and link a green CI run.
- Update [`CHANGELOG.md`](./CHANGELOG.md) `[Unreleased]` with one bullet
  per user-visible change.
- Wait for CI green (`ci.yml` + `integration.yml` + `codeql.yml`) before
  requesting review.

## Releasing

Tag-driven. See the *Tagging convention* in
[docs/ROADMAP.md](./docs/ROADMAP.md):

| Tag | Meaning | PyPI? | GitHub Release? |
|---|---|---|---|
| `milestone/m<N>` | Dev checkpoint, bisect marker | ❌ | ❌ |
| `vX.Y.Z` | Shippable release | ✅ | ✅ |

A `release.yml` workflow with PyPI Trusted Publishing is on the M8b
roadmap (separate PR). Until it lands, releases use the documented PyPI
token flow noted in [`CHANGELOG.md`](./CHANGELOG.md).
