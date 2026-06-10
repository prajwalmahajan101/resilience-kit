"""Shared testcontainers helpers for adapter integration suites.

The Redis / Valkey fixtures live in ``conftest.py`` because every
integration test in this folder needs them. Postgres is only needed by
the adapter suites under ``tests/integration/fastapi_app/`` (M5) and
``tests/integration/django_app/`` (M6), so the fixture lives here and is
imported on demand by each adapter's own ``conftest.py``.

Both adapters need an identical Postgres setup: a session-scoped
container, a DSN string, and skip-if-Docker-missing semantics that mirror
the Redis fixture. Centralising the helper keeps the two adapter
``conftest`` files thin and ensures Postgres version drift only has to
be fixed once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[object]:
    """Spin a Postgres container for the session.

    Yields:
        The running container so individual tests can introspect its
        host/port if they need more than the bare DSN.
    """
    testcontainers_postgres = pytest.importorskip(
        "testcontainers.postgres",
        reason="testcontainers[postgresql] not installed; skipping adapter integration tests",
    )
    container = testcontainers_postgres.PostgresContainer("postgres:16")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture
def postgres_dsn(postgres_container: object) -> str:
    """Return an asyncpg-style DSN for the running Postgres container.

    Args:
        postgres_container: Session-scoped Postgres container.

    Returns:
        ``postgresql://user:pass@host:port/db`` — accepted by both
        asyncpg (M4 audit backend) and SQLAlchemy 2.x (M5
        ``EncryptedString`` integration test).
    """
    # ``get_connection_url`` returns a SQLAlchemy URL with the
    # ``postgresql+psycopg2`` driver hint; strip it so asyncpg accepts the
    # DSN unchanged.
    url = postgres_container.get_connection_url()  # type: ignore[attr-defined]
    return url.replace("postgresql+psycopg2://", "postgresql://")
