# 0001 — Protocols, not ABCs

Status: accepted  ·  Date: 2026-06-10 (backfilled)  ·  Milestone: M1

## Context

The kit ships ~9 swappable subsystems — cache backend, circuit-breaker
backend, throttle backend, audit sink, audit sanitizer, metrics sink,
settings source, clock, audit dispatcher — and intends third parties to
ship their own implementations as separate PyPI packages. Two shapes were
on the table:

1. `abc.ABC` base classes with `@abstractmethod` declarations. Third
   parties subclass them.
2. `typing.Protocol` definitions. Third parties match the shape; no
   inheritance, no import-time coupling to the kit.

Inheritance ties every third-party implementation to the kit as a hard
import. A protocol rename, an abstract-method signature change, or even
a `MyMeta(ABCMeta)` clash in a downstream package becomes a breaking
change. The kit also resolves implementations dynamically via entry
points (see ADR 0004) — at resolution time the kit only has a class
object and a settings name, not a known base class.

## Decision

Every swappable subsystem is a `typing.Protocol`. Implementations declare
no relationship to the protocol; structural typing is sufficient. Type
checkers (`mypy --strict`) enforce the shape statically at the
implementation site. The kit never calls `isinstance(impl, AsyncCache)`
on a third-party object — it trusts the protocol-shaped duck.

Where the kit *does* need a runtime check (e.g. the provider chain
distinguishing "callable factory" from "instance"), it checks the
concrete attribute that decides behaviour, not the protocol identity.

## Consequences

- Third-party backends import zero kit code at definition time. A
  `MyMemcachedCache` class can sit in `rk_memcached/cache.py` with no
  `from resilience_kit ...` import.
- Mock backends in tests are one-line classes — no `MagicMock(spec=...)`
  needed to satisfy abstract methods.
- Protocol additions are *not* automatically breaking — a new method on
  `AsyncCache` is enforced only by mypy on opt-in implementers, not by
  Python's class-creation machinery. We treat protocol additions as
  breaking anyway and bump the locked-API minor.
- Type checkers must run for the contract to hold. `mypy --strict` on
  `src` is wired into pre-commit and CI.

## Usage

```python
from typing import Protocol

class AsyncCache(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None: ...
    async def incr(self, key: str, amount: int = 1) -> int: ...
    async def delete(self, key: str) -> None: ...
    async def health_check(self) -> bool: ...
```

Implementer in a third-party package — no inheritance:

```python
class MemcachedCache:
    async def get(self, key): ...
    async def set(self, key, value, ttl=None): ...
    async def incr(self, key, amount=1): ...
    async def delete(self, key): ...
    async def health_check(self): ...
```

Wired via entry point (ADR 0004); resolved at runtime by
`resilience_kit._providers.resolve_provider`.
