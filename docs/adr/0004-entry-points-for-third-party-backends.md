# 0004 — Entry points for third-party backends

Status: accepted  ·  Date: 2026-06-10 (backfilled)  ·  Milestone: M2 / M4

## Context

Operators select backends by name at runtime — `RESILIENCE_BACKEND=redis`
or `RESILIENCE_AUDIT__SINK=postgres`. The kit must resolve the name to
a class without importing any backend that isn't installed (an absent
`redis-py` must not prevent `import resilience_kit`).

Three resolution strategies were considered:

1. **Hard-coded registry dict** in the kit. Adding a backend requires a
   kit release. Third parties can't extend the kit without a fork.
2. **Plugin directory at runtime.** Scan a config-defined path for `.py`
   files. Security hazard, import-order hazard, hard to test.
3. **`importlib.metadata` entry points.** Standard Python packaging.
   Third parties declare entries in their own `pyproject.toml`; the
   kit reads them at resolution time, not at import time.

The kit also needs the same resolution path for *its own* builtins so
the code path is exercised on every test run — not just by hypothetical
third parties.

## Decision

Six entry-point groups in `pyproject.toml`:

- `resilience_kit.cache_backends`
- `resilience_kit.breaker_backends`
- `resilience_kit.throttle_backends`
- `resilience_kit.audit_backends`
- `resilience_kit.audit_sanitizers`
- `resilience_kit.metrics_sinks`

(Plus `resilience_kit.settings_sources` declared empty as an extension
hook — see comment in `pyproject.toml`.)

The kit publishes its own builtins in these groups so they go through
the same resolution chain as any third-party entry.

Resolution chain implemented in `src/resilience_kit/_providers.py`,
`resolve_provider()`:

1. Explicit callable or instance passed in by the caller.
2. Importable string `"pkg.mod:ClassName"` from settings.
3. **Entry-point lookup** by name in the configured group.
4. Builtin name lookup (kit-shipped fallback).
5. Raise `UnknownBackendError` with the list of available names.

**Entry points are checked before builtins.** A third-party package
that registers `memory` in `resilience_kit.cache_backends` will shadow
the kit's own `memory` backend. This is intentional — it lets a third
party ship a drop-in replacement — but it is a footgun for name
collisions. See [LLD.md §3](../LLD.md) and the docstring in
`_providers.py`.

## Consequences

- Zero-fork extensibility. A third party publishes `rk-memcached` with
  one entry-point declaration and the kit discovers it.
- Discovery is `O(installed-packages)` at resolution time; cached by
  `importlib.metadata` after first call. Not measurable in startup.
- Shadowing builtins is by design; operators who run a third-party
  backend with a builtin's name see their backend win. The kit's
  contract suite parametrizes over both kit builtins and a fake
  third-party backend (`tests/fixtures/fake_third_party/`) to cover
  both paths in CI.
- Operators should namespace third-party backend names (`acme-redis`,
  not `redis`) to avoid accidental shadowing.

## Usage

Third-party publisher declares an entry point:

```toml
# in their own pyproject.toml
[project.entry-points."resilience_kit.cache_backends"]
memcached = "rk_memcached:MemcachedCache"
```

Operator wires it by name:

```bash
pip install rk-memcached
export RESILIENCE_CACHE__BACKEND=memcached
```

The kit's own builtins use the same surface:

```toml
[project.entry-points."resilience_kit.cache_backends"]
memory = "resilience_kit.cache.memory_impl:InMemoryCache"
redis  = "resilience_kit.cache.redis_impl:RedisCache"
```
