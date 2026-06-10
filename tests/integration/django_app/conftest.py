"""Fixtures for the Django adapter integration suite.

Spins postgres:16 via the shared testcontainers fixture, then exports
its connection details into the env vars the test settings module
reads at import time. Django is bootstrapped lazily inside the
``django_app`` fixture so the postgres container is already running
before ``django.setup()`` validates the DATABASES dict.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import pytest

from tests.integration._containers import postgres_container

if TYPE_CHECKING:
    from collections.abc import Iterator


__all__ = ["postgres_container"]


@pytest.fixture(scope="session")
def django_db_setup() -> None:
    """Override pytest-django's automatic DB creation — we manage it ourselves."""
    return


@pytest.fixture(scope="session")
def django_app(postgres_container: object) -> Iterator[None]:
    """Bootstrap Django against the running postgres container."""
    raw_url = postgres_container.get_connection_url()  # type: ignore[attr-defined]
    dsn = raw_url.replace("postgresql+psycopg2://", "postgresql://")
    parsed = urlparse(dsn)
    os.environ["M6_PG_HOST"] = parsed.hostname or "localhost"
    os.environ["M6_PG_PORT"] = str(parsed.port or 5432)
    os.environ["M6_PG_DB"] = (parsed.path or "/test").lstrip("/")
    os.environ["M6_PG_USER"] = parsed.username or "test"
    os.environ["M6_PG_PASSWORD"] = parsed.password or "test"
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "tests.integration.django_app.settings_module",
    )
    os.environ.setdefault("RESILIENCE_CRYPTO__ENVIRONMENT", "test")

    import django  # noqa: PLC0415

    django.setup()
    from django.apps import apps  # noqa: PLC0415
    from django.db import connection  # noqa: PLC0415

    # Build the table directly from the model instead of running through
    # migrations — keeps the test self-contained without needing a
    # migrations/ directory on the test-only app.
    with connection.schema_editor() as schema_editor:
        secret_model = apps.get_model("django_app", "Secret")
        schema_editor.create_model(secret_model)
    yield
    with connection.schema_editor() as schema_editor:
        schema_editor.delete_model(secret_model)
    os.environ.pop("RESILIENCE_CRYPTO__ENVIRONMENT", None)
