# 0010 — FastAPI adapter shape

Status: proposed  ·  Date: 2026-06-10  ·  Milestone: M5

## Context

M0–M4 shipped a framework-agnostic kit: a `RecoveryMonitor` singleton, an
audit dispatcher, a `health_snapshot()` aggregator, six ASGI middleware
classes, a `ResilienceRegistry`, decorators (`@resilient`,
`@retry_on_failure`, `@circuit_breaker`), `AsyncAPIClient`, and
`FernetCipher`. To prove the public surfaces are right — and to give
adopters a one-import experience — M5 ships a FastAPI adapter that wires
those primitives into FastAPI's lifespan, dependency, middleware, and
exception-handler hooks.

The adapter must be pure glue: ≲ 500 LOC, zero business logic,
copy-paste-friendly. If wiring it forces a primitive change in the kit,
that primitive is wrong — not the adapter.

This ADR captures the public shape of `resilience_kit.adapters.fastapi`
and the small set of irreversible choices that shape will lock in (which
side of the API owns lifespan, which exception-status table the handler
reads from, how the SQLAlchemy `EncryptedString` integrates with
`FernetCipher`).

## Decision

_To be filled by the M5 execution branch (`feat/m5-fastapi-adapter`)._

## Consequences

_To be filled by the M5 execution branch._

## Usage

_To be filled by the M5 execution branch._
