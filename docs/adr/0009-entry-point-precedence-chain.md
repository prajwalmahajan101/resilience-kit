# 0009 — Entry-point precedence chain for backends

Status: accepted  ·  Date: 2026-06-09  ·  Milestone: M4

## Context

The kit ships builtins for every swappable subsystem (cache, breaker,
throttle, audit, sanitizer, metrics sink, settings source) and wants
third parties to be able to publish their own backends via the standard
Python entry-point mechanism — without having to fork the kit, without
having to import their package upfront, and without ambiguity about
which backend resolves when names collide.

## Decision

`resilience_kit._providers.resolve_provider` resolves a backend name in
**exactly this order**, stopping at the first match:

1. **Explicit instance / callable.** Anything passed as `name` that is
   not a `str` is treated as ready-made and returned directly (after a
   factory call if it's callable). Callers who want absolute control
   pass an instance.
2. **Importable string** of the form `"pkg.mod:Class"`. Imported,
   asserted callable, called with the factory kwargs.
3. **Entry-point lookup.** `importlib.metadata.entry_points(group=...)`
   filtered by `name`. The first match wins.
4. **Builtin.** Kit-shipped name → constructor in the builtins map
   passed by the caller.
5. **Fail.** `UnknownBackendError` listing every name reachable via the
   entry-point group + the builtins, sorted, so the error message
   itself is a hint to the operator.

The kit publishes every builtin as an entry point too. So a third-party
backend named `"memory"` would still lose to the kit's `"memory"`
because step 4 fires before any user-published EP with the same name —
**a kit-shipped builtin name is reserved**. Third-party authors pick a
distinct name (`fake`, `s3`, `dogstatsd`, …).

## Consequences

- Plain `RESILIENCE_BACKEND=fake` works for any installed plugin once
  the operator adds it to the dependency manifest; no code change is
  needed inside the kit.
- The kit can ship its own builtins as entry points too, which means
  one shape end-to-end and one test (`tests/contract/test_provider_chain.py`)
  that proves the chain works against a real installed distribution
  (`tests/fixtures/fake_third_party`).
- A kit-shipped builtin name (`memory`, `noop`, `default`, …) cannot
  be overridden by a third-party EP. That is a *feature* — operators
  who install a misbehaving plugin should not silently change the
  kit's defaults — but is documented as a constraint in
  `docs/CONTRIBUTING.md`.
- `UnknownBackendError.available` is the union of EP + builtin names so
  callers logging the error get the menu of fixes for free.

## Usage

A third party publishing a cache backend:

```toml
# their_package/pyproject.toml
[project.entry-points."resilience_kit.cache_backends"]
s3 = "their_package.cache:S3Cache"
```

After `pip install their-package`:

```bash
RESILIENCE_BACKEND=s3
RESILIENCE_REDIS_URL=...
```

The kit resolves `s3` via step 3 of the chain. No kit changes required.

```python
from resilience_kit._providers import resolve_provider
from resilience_kit.cache.memory_impl import InMemoryAsyncCache

backend = resolve_provider(
    group="resilience_kit.cache_backends",
    name="s3",  # third-party
    builtins={"memory": InMemoryAsyncCache},
)
```
