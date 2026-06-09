"""Integration test for the Postgres audit backend (ROADMAP M4 exit gate).

Spins ``testcontainers-postgresql``, applies :data:`SCHEMA_SQL`, wires
the kit's audit dispatcher to write through
:class:`PostgresAuditBackend`, and asserts a sanitized row lands when
``@log_outbound`` fires.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("asyncpg")
pytest.importorskip("testcontainers.postgres")

import asyncpg

from resilience_kit.audit import AuditEvent, set_dispatcher
from resilience_kit.audit.backends.postgres import SCHEMA_SQL, PostgresAuditBackend
from resilience_kit.audit.dispatch import InlineDispatcher

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_dsn() -> Iterator[str]:
    """Spin a Postgres container for the module; yield the DSN."""
    pg = pytest.importorskip(
        "testcontainers.postgres",
        reason="testcontainers[postgresql] not installed",
    )
    container = pg.PostgresContainer("postgres:16-alpine")
    container.start()
    try:
        dsn = container.get_connection_url().replace(
            "postgresql+psycopg2://",
            "postgresql://",
        )
        yield dsn
    finally:
        container.stop()


@pytest.fixture
async def backend(postgres_dsn: str) -> AsyncIterator[PostgresAuditBackend]:
    """Apply the migration and yield a configured backend."""
    setup_conn = await asyncpg.connect(postgres_dsn)
    try:
        await setup_conn.execute(SCHEMA_SQL)
        await setup_conn.execute("TRUNCATE resilience_kit_audit RESTART IDENTITY")
    finally:
        await setup_conn.close()
    backend = PostgresAuditBackend(postgres_dsn)
    try:
        yield backend
    finally:
        await backend.aclose()


@pytest.mark.asyncio
async def test_log_outbound_writes_a_sanitised_row(
    backend: PostgresAuditBackend,
    postgres_dsn: str,
) -> None:
    """Exit-gate: a dispatched event lands in the table with the payload sanitised."""
    dispatcher = InlineDispatcher(backend)
    set_dispatcher(dispatcher)

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
        payload={"user": "alice", "password": "p"},
        details={"host": "partner.example"},
    )
    dispatcher.submit(event)
    await dispatcher.flush()

    conn = await asyncpg.connect(postgres_dsn)
    try:
        rows = await conn.fetch(
            "SELECT service, request_id, payload, details FROM resilience_kit_audit",
        )
    finally:
        await conn.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["service"] == "partner"
    assert row["request_id"] == "rq-1"
    # payload + details come back as JSON strings from asyncpg's default codec.
    import json  # noqa: PLC0415

    payload = json.loads(row["payload"])
    assert payload["user"] == "alice"
    assert payload["password"] == "[REDACTED]"
    details = json.loads(row["details"])
    assert details["host"] == "partner.example"
