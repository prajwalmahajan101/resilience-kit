"""Postgres audit backend — asyncpg writer with batched ``COPY`` (extra: audit-postgres).

The backend opens an :class:`asyncpg.Pool` lazily on first write and
reuses it for the lifetime of the process. Each call to
:meth:`write_many` writes the batch atomically as a single transaction —
``executemany`` against a prepared insert, not raw ``COPY``, because
``COPY`` does not play well with ``jsonb`` casting in asyncpg's
auto-prepared statement cache.

The schema migration is shipped as a docstring constant
(:data:`SCHEMA_SQL`) — callers run it via their own migration tool. The
kit does NOT auto-create the table at startup; that would conflict with
schema-managed deployments.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from resilience_kit.circuit_breaker.base import HealthSnapshot
from resilience_kit.exceptions import MissingExtraError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from resilience_kit.audit.backends.base import AuditEvent

try:
    import asyncpg
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError(
        "audit-postgres",
        "resilience-kit[audit-postgres]",
    ) from exc


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS resilience_kit_audit (
    id            BIGSERIAL PRIMARY KEY,
    timestamp     TIMESTAMPTZ NOT NULL,
    direction     TEXT        NOT NULL,
    service       TEXT        NOT NULL,
    method        TEXT,
    path          TEXT,
    outcome       TEXT        NOT NULL,
    status        INTEGER,
    error_code    TEXT,
    error_class   TEXT,
    request_id    TEXT,
    correlation_id TEXT,
    latency_ms    DOUBLE PRECISION NOT NULL,
    payload       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    details       JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audit_service_timestamp
    ON resilience_kit_audit (service, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_request_id
    ON resilience_kit_audit (request_id);
"""

_INSERT_SQL = """
INSERT INTO resilience_kit_audit (
    timestamp, direction, service, method, path, outcome,
    status, error_code, error_class, request_id, correlation_id,
    latency_ms, payload, details
) VALUES (
    to_timestamp($1), $2, $3, $4, $5, $6,
    $7, $8, $9, $10, $11,
    $12, $13::jsonb, $14::jsonb
)
"""


class PostgresAuditBackend:
    """asyncpg-backed audit storage.

    The pool is built lazily on first :meth:`write_many` so the backend
    can be instantiated at import time (provider chain) without forcing
    an event loop or network access.
    """

    def __init__(
        self,
        dsn: str | None = None,
        *,
        table: str = "resilience_kit_audit",
        min_pool_size: int = 1,
        max_pool_size: int = 5,
    ) -> None:
        """Configure the backend.

        Args:
            dsn: Postgres DSN — when ``None``, the backend reads
                ``settings.audit_postgres_dsn`` (placeholder for future
                top-level settings field; for now callers MUST pass dsn
                explicitly).
            table: Target table name. The shipped migration uses
                ``resilience_kit_audit``; override only when integrating
                into a multi-tenant schema.
            min_pool_size: ``asyncpg.create_pool`` minimum size.
            max_pool_size: ``asyncpg.create_pool`` maximum size.

        Raises:
            ValueError: ``dsn`` is unset.
        """
        if dsn is None:
            msg = "PostgresAuditBackend requires a DSN."
            raise ValueError(msg)
        self._dsn = dsn
        self._table = table
        self._min = min_pool_size
        self._max = max_pool_size
        self._pool: asyncpg.Pool | None = None
        # asyncio.Lock (not threading.Lock): a threading.Lock is released the
        # moment ``await`` suspends, so concurrent first writes could both pass
        # the guard, both ``await create_pool``, and leak the orphaned pool.
        self._pool_lock = asyncio.Lock()

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        # Double-checked locking is fine here — pool creation is idempotent
        # but expensive, so we serialise across concurrent first writes.
        async with self._pool_lock:
            if self._pool is None:
                self._pool = await asyncpg.create_pool(
                    self._dsn,
                    min_size=self._min,
                    max_size=self._max,
                )
        assert self._pool is not None
        return self._pool

    async def write(self, event: AuditEvent) -> None:
        """Persist a single event (delegates to :meth:`write_many`)."""
        await self.write_many([event])

    async def write_many(self, events: Sequence[AuditEvent]) -> None:
        """Persist a batch as a single transaction."""
        if not events:
            return
        pool = await self._ensure_pool()
        rows = [_event_to_row(e) for e in events]
        async with pool.acquire() as conn, conn.transaction():
            await conn.executemany(self._insert_sql, rows)

    async def health_check(self) -> HealthSnapshot:
        """Return a snapshot reflecting whether ``SELECT 1`` succeeds."""
        try:
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                value = await conn.fetchval("SELECT 1")
        except Exception as exc:
            return HealthSnapshot(
                healthy=False,
                backend="postgres",
                detail=f"{type(exc).__name__}: {exc}",
            )
        return HealthSnapshot(healthy=bool(value == 1), backend="postgres")

    async def aclose(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def _insert_sql(self) -> str:
        return _INSERT_SQL.replace("resilience_kit_audit", self._table)


def _event_to_row(event: AuditEvent) -> tuple[object, ...]:
    return (
        event.timestamp,
        event.direction,
        event.service,
        event.method or None,
        event.path or None,
        event.outcome,
        event.status,
        event.error_code,
        event.error_class,
        event.request_id,
        event.correlation_id,
        event.latency_ms,
        json.dumps(dict(event.payload)),
        json.dumps(dict(event.details)),
    )


__all__ = ["SCHEMA_SQL", "PostgresAuditBackend"]
