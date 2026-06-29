"""Unit-level tests for :mod:`resilience_kit.audit.backends.postgres`.

The real integration test (testcontainers Postgres) lives at
``tests/integration/test_audit_postgres.py`` and is part of M4's exit
gate; these unit tests only cover the wiring that does not need a live
DB (DSN-required guard, row shape, SQL retargeting).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

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


@pytest.mark.asyncio
async def test_ensure_pool_serialises_concurrent_first_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent first writes create exactly one pool (#B7).

    A ``threading.Lock`` is released the instant ``await`` suspends, so two
    coroutines racing through ``_ensure_pool`` would both create a pool and
    leak one. The ``asyncio.Lock`` must serialise them into a single
    ``create_pool`` call.
    """
    backend = PostgresAuditBackend(dsn="postgresql://invalid/invalid")

    async def slow_create_pool(*_args: object, **_kwargs: object) -> object:
        # Yield control so a broken lock lets the second coroutine slip past
        # the ``is None`` guard before the first finishes.
        await asyncio.sleep(0)
        return AsyncMock(name="pool")

    create_pool = AsyncMock(side_effect=slow_create_pool)
    monkeypatch.setattr("asyncpg.create_pool", create_pool)

    pools = await asyncio.gather(backend._ensure_pool(), backend._ensure_pool())

    assert create_pool.call_count == 1
    assert pools[0] is pools[1]
