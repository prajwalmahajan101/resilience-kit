"""Unit tests for :class:`resilience_kit.audit.backends.StdlibLoggingAuditBackend`."""

from __future__ import annotations

import logging

import pytest

from resilience_kit.audit.backends.base import AuditEvent
from resilience_kit.audit.backends.stdlib_logging import StdlibLoggingAuditBackend


def _event(**overrides: object) -> AuditEvent:
    base = {
        "direction": "outbound",
        "service": "partner",
        "method": "GET",
        "path": "/v1/x",
        "outcome": "success",
        "latency_ms": 12.3,
        "status": 200,
    }
    base.update(overrides)
    return AuditEvent(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_write_many_emits_one_record_per_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each event lands as one INFO record on the configured logger."""
    backend = StdlibLoggingAuditBackend()
    with caplog.at_level(logging.INFO, logger="resilience_kit.audit"):
        await backend.write_many([_event(), _event(method="POST")])
    audit_records = [r for r in caplog.records if r.name == "resilience_kit.audit"]
    assert len(audit_records) == 2
    assert "outbound partner GET /v1/x" in audit_records[0].getMessage()


@pytest.mark.asyncio
async def test_event_fields_in_extra(caplog: pytest.LogCaptureFixture) -> None:
    """Structured fields are attached as ``extra={"audit_event": ...}``."""
    backend = StdlibLoggingAuditBackend()
    with caplog.at_level(logging.INFO, logger="resilience_kit.audit"):
        await backend.write_many([_event(status=503, outcome="failure")])
    record = next(r for r in caplog.records if r.name == "resilience_kit.audit")
    payload = record.audit_event  # type: ignore[attr-defined]
    assert payload["status"] == 503
    assert payload["outcome"] == "failure"


@pytest.mark.asyncio
async def test_health_check_always_healthy() -> None:
    """Logging backend cannot be unhealthy from the kit's perspective (#B4)."""
    snap = await StdlibLoggingAuditBackend().health_check()
    assert snap.healthy is True
    assert snap.backend == "stdlib_logging"


@pytest.mark.asyncio
async def test_logger_name_override(caplog: pytest.LogCaptureFixture) -> None:
    """Caller-supplied logger name routes records elsewhere."""
    backend = StdlibLoggingAuditBackend(logger_name="custom.audit")
    with caplog.at_level(logging.INFO, logger="custom.audit"):
        await backend.write_many([_event()])
    assert any(r.name == "custom.audit" for r in caplog.records)
