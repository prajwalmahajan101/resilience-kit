"""Audit backend contract — same write/health shape across noop, stdlib_logging, postgres.

The Postgres backend can only be exercised against a live DB; the
testcontainers integration test covers that. Here we lock the shape
that every backend MUST satisfy: accept any :class:`AuditEvent` from
``write_many`` without raising, and report ``health_check`` as bool.
"""

from __future__ import annotations

import pytest

from resilience_kit.audit.backends import (
    AuditEvent,
    NoopAuditBackend,
    StdlibLoggingAuditBackend,
)


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


@pytest.mark.asyncio
async def test_write_many_accepts_a_batch(backend: object) -> None:
    """Every backend accepts a non-empty batch without raising."""
    await backend.write_many([_event(), _event()])  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_write_many_accepts_empty_batch(backend: object) -> None:
    """Empty batch is a no-op (dispatcher may flush an empty list on shutdown)."""
    await backend.write_many([])  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_health_check_returns_bool(backend: object) -> None:
    """``health_check`` returns ``True`` / ``False`` (not ``None``)."""
    result = await backend.health_check()  # type: ignore[attr-defined]
    assert isinstance(result, bool)
