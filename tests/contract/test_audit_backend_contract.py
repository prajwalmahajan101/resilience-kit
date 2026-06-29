"""Audit backend contract — same write/health shape across noop, stdlib_logging, postgres.

The Postgres backend can only be exercised against a live DB; the
testcontainers integration test covers that. Here we lock the shape
that every backend MUST satisfy: structurally satisfy the
:class:`AuditBackend` protocol, accept any :class:`AuditEvent` from
``write`` / ``write_many`` without raising, and report ``health_check``
as a :class:`HealthSnapshot` (#B4).
"""

from __future__ import annotations

import pytest

from resilience_kit.audit.backends import (
    AuditEvent,
    NoopAuditBackend,
    StdlibLoggingAuditBackend,
)
from resilience_kit.audit.backends.base import AuditBackend
from resilience_kit.circuit_breaker.base import HealthSnapshot


def _event() -> AuditEvent:
    return AuditEvent(
        direction="outbound",
        service="partner",
        method="GET",
        path="/v1/x",
        outcome="success",
        latency_ms=1.0,
        status=200,
        payload={"k": "v"},
        details={"host": "partner.example"},
    )


@pytest.fixture(
    params=[
        pytest.param(NoopAuditBackend, id="noop"),
        pytest.param(StdlibLoggingAuditBackend, id="stdlib_logging"),
    ],
)
def backend(request: pytest.FixtureRequest) -> object:
    """Yield a freshly-built backend for the parametrised contract test."""
    return request.param()


def test_satisfies_audit_backend_protocol(backend: object) -> None:
    """Every kit backend structurally satisfies the AuditBackend protocol (#B4)."""
    assert isinstance(backend, AuditBackend)


@pytest.mark.asyncio
async def test_write_persists_single_event(backend: object) -> None:
    """`write` accepts a single event without raising (delegates to write_many)."""
    await backend.write(_event())  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_write_many_accepts_a_batch(backend: object) -> None:
    """Every backend accepts a non-empty batch without raising."""
    await backend.write_many([_event(), _event()])  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_write_many_accepts_empty_batch(backend: object) -> None:
    """Empty batch is a no-op (dispatcher may flush an empty list on shutdown)."""
    await backend.write_many([])  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_health_check_returns_snapshot(backend: object) -> None:
    """``health_check`` returns a :class:`HealthSnapshot`, not a bare bool (#B4)."""
    result = await backend.health_check()  # type: ignore[attr-defined]
    assert isinstance(result, HealthSnapshot)
    assert result.healthy is True
