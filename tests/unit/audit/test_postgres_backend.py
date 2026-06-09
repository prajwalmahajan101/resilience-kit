"""Unit-level tests for :mod:`resilience_kit.audit.backends.postgres`.

The real integration test (testcontainers Postgres) lives at
``tests/integration/test_audit_postgres.py`` and is part of M4's exit
gate; these unit tests only cover the wiring that does not need a live
DB (DSN-required guard, row shape, SQL retargeting).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("asyncpg")

from resilience_kit.audit.backends.base import AuditEvent
from resilience_kit.audit.backends.postgres import (
    SCHEMA_SQL,
    PostgresAuditBackend,
    _event_to_row,
)


def test_dsn_required() -> None:
    """A missing DSN is a configuration error, not silent."""
    with pytest.raises(ValueError, match="requires a DSN"):
        PostgresAuditBackend(None)


def test_schema_sql_contains_table() -> None:
    """The shipped migration string defines the canonical table."""
    assert "CREATE TABLE IF NOT EXISTS resilience_kit_audit" in SCHEMA_SQL
    assert "jsonb" in SCHEMA_SQL.lower()


def test_event_to_row_serialises_jsonb_payloads() -> None:
    """payload + details land as JSON strings ready for ``::jsonb`` casts."""
    event = AuditEvent(
        direction="outbound",
        service="partner",
        method="POST",
        path="/v1/x",
        outcome="success",
        latency_ms=12.3,
        status=200,
        request_id="rq-1",
        correlation_id="corr-1",
        payload={"k": "v"},
        details={"host": "partner.example"},
    )
    row = _event_to_row(event)
    assert row[1] == "outbound"
    assert row[2] == "partner"
    assert json.loads(row[12]) == {"k": "v"}  # type: ignore[arg-type]
    assert json.loads(row[13]) == {"host": "partner.example"}  # type: ignore[arg-type]


def test_table_override_retargets_insert_sql() -> None:
    """``table=`` rewrites the insert statement against the custom name."""
    backend = PostgresAuditBackend(
        dsn="postgresql://invalid/invalid",
        table="custom_audit",
    )
    sql = backend._insert_sql
    assert "custom_audit" in sql
    assert "resilience_kit_audit" not in sql
