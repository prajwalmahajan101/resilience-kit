"""Audit backends — the storage layer behind :class:`~resilience_kit.audit.AuditBackend`.

Builtins: :class:`NoopAuditBackend` (default — drop events on the floor)
and :class:`StdlibLoggingAuditBackend` (commit 5). The Postgres backend
ships behind the ``audit-postgres`` extra (commit 14).
"""

from __future__ import annotations

from resilience_kit.audit.backends.base import AuditBackend, AuditEvent
from resilience_kit.audit.backends.noop import NoopAuditBackend
from resilience_kit.audit.backends.stdlib_logging import StdlibLoggingAuditBackend

__all__ = [
    "AuditBackend",
    "AuditEvent",
    "NoopAuditBackend",
    "StdlibLoggingAuditBackend",
]

# PostgresAuditBackend is exposed under the `audit-postgres` extra; importing
# the package without asyncpg installed must not raise. Users access it via
# `from resilience_kit.audit.backends.postgres import PostgresAuditBackend`.
