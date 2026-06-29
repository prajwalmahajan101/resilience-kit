"""Unit tests for the audit protocol + the no-op backend."""

from __future__ import annotations

import pytest

from resilience_kit.audit.backends.base import AuditBackend, AuditEvent
from resilience_kit.audit.backends.noop import NoopAuditBackend


def test_audit_event_defaults() -> None:
    """Default factories fill payload / details / timestamp."""
    event = AuditEvent(
        direction="outbound",
        service="partner",
        method="GET",
        path="/v1/x",
        outcome="success",
        latency_ms=12.3,
    )
    assert event.payload == {}
    assert event.details == {}
    assert event.timestamp > 0


def test_noop_backend_implements_protocol() -> None:
    """NoopAuditBackend satisfies the AuditBackend Protocol at runtime."""
    assert isinstance(NoopAuditBackend(), AuditBackend)


@pytest.mark.asyncio
async def test_noop_backend_is_healthy() -> None:
    """No-op backend reports a healthy HealthSnapshot (#B4)."""
    snap = await NoopAuditBackend().health_check()
    assert snap.healthy is True
    assert snap.backend == "noop"


@pytest.mark.asyncio
async def test_noop_backend_write_many_is_a_noop() -> None:
    """write_many drops events without raising."""
    backend = NoopAuditBackend()
    event = AuditEvent(
        direction="inbound",
        service="api",
        method="POST",
        path="/v1/create",
        outcome="success",
        latency_ms=1.0,
    )
    await backend.write_many([event])
