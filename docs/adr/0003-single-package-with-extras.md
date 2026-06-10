# 0003 — Single package, many optional extras

Status: accepted  ·  Date: 2026-06-10 (backfilled)  ·  Milestone: M0

## Context

The kit ships ~8 optional backends — redis/valkey, pybreaker, httpx,
requests, cryptography, asyncpg, Django, FastAPI — and could be
distributed three ways:

1. **One package with optional extras.** `pip install
   "resilience-kit[fastapi,redis]"` pulls the right deps.
2. **Micro-packages.** `resilience-kit-core` + `resilience-kit-redis`
   + `resilience-kit-fastapi`, each with its own version.
3. **Namespaced plugins.** `resilience_kit` as a namespace package with
   `rk-redis`, `rk-fastapi` as siblings.

Micro-packages multiply release work (N releases per change), version-
skew matrices (which `rk-redis` works with which `rk-core`?), and
contributor friction (clone N repos to debug one issue). Namespace
packages share that pain plus the `__path__` machinery hazards.

The kit is small — at v0.1 the entire `src/` tree fits in one head.
CLAUDE.md sets a re-evaluation threshold of 350+ files.

## Decision

Single package `resilience-kit` on PyPI. Optional dependency groups in
`pyproject.toml` `[project.optional-dependencies]`:

| Extra | Pulls |
|---|---|
| *(none)* | core: pure-Python primitives, in-memory backends, middleware |
| `[redis]` | `redis-py >= 5` |
| `[pybreaker]` | `pybreaker` |
| `[http]` | `httpx >= 0.27, < 0.29` |
| `[requests]` | `requests` |
| `[crypto]` | `cryptography` |
| `[audit-postgres]` | `asyncpg` |
| `[django]` | `Django >= 4.2` + DRF |
| `[fastapi]` | `fastapi` + `starlette` |
| `[all]` | everything above |
| `[dev]` | tooling (pytest, mypy, ruff, testcontainers, …) |

Submodule imports that need an absent extra raise `MissingExtraError`
at import time with the exact `pip install` hint — no deep
`ModuleNotFoundError` in a stack trace.

## Consequences

- One PyPI release per kit change. One CHANGELOG, one tag, one set of
  release notes.
- Downstream pins are simple: `resilience-kit==0.1.0`. No
  `resilience-kit-core ~= 0.1.0, resilience-kit-redis ~= 0.1.0` skew.
- Importing the kit without `[http]` or `[crypto]` works — lazy
  attribute resolution in `src/resilience_kit/__init__.py` defers those
  modules until first access.
- One CI matrix. The verify-extras-matrix pre-commit hook installs each
  extra in a clean venv to confirm declared deps are sufficient.
- Re-evaluate at 350+ files (CLAUDE.md) — splitting later is mechanical
  once the protocols are stable.

## Usage

```bash
pip install resilience-kit                        # core only
pip install "resilience-kit[fastapi,redis,http]"  # FastAPI on Valkey
pip install "resilience-kit[django,redis,http]"   # Django on Valkey
pip install "resilience-kit[all]"                 # everything
```

Importing a backend whose extra is missing surfaces the install hint:

```pycon
>>> from resilience_kit.cache import redis_impl  # without [redis]
MissingExtraError: install resilience-kit[redis]
```
