"""Fixtures shared by the FastAPI adapter integration tests."""

from __future__ import annotations

from tests.integration._containers import postgres_container, postgres_dsn

__all__ = ["postgres_container", "postgres_dsn"]
