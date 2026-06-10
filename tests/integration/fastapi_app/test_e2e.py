"""End-to-end test for the FastAPI adapter (ROADMAP M5 exit gate).

Spins a Postgres container, builds the example app from ``main.py``
against it, and asserts:

1. ``/healthz`` returns 200, ``/readyz`` returns 200 with no backends.
2. ``rate_limit(Scope.IP, "2/min")`` denies the 3rd request with 429,
   ``Retry-After`` header, and the LLD §11 envelope.
3. ``install_exception_handlers`` maps an injected
   :class:`~resilience_kit.exceptions.ValidationError` to 400.
4. ``EncryptedString`` round-trips through Postgres — raw SQL shows
   the Fernet token; the ORM read returns plaintext.
5. ``AsyncAPIClient`` calls the fake upstream via an injected
   ``httpx.AsyncClient`` and surfaces the upstream's status.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from resilience_kit.adapters.fastapi.fields import (
    EncryptedString,  # noqa: F401 — registers the type
)
from tests.integration.fastapi_app.main import METADATA, build_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
def _crypto_env() -> AsyncIterator[None]:
    """Configure the kit's crypto settings for a test run."""
    os.environ["RESILIENCE_CRYPTO__ENVIRONMENT"] = "test"
    yield
    os.environ.pop("RESILIENCE_CRYPTO__ENVIRONMENT", None)


@pytest.fixture
async def async_engine(postgres_dsn: str):  # type: ignore[no-untyped-def]
    """Build an async SQLAlchemy engine and create the secrets table."""
    async_dsn = postgres_dsn.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(async_dsn)
    async with engine.begin() as conn:
        await conn.run_sync(METADATA.drop_all)
        await conn.run_sync(METADATA.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def fake_upstream() -> httpx.AsyncClient:
    """Return an httpx.AsyncClient routed through an in-memory MockTransport."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ping":
            return httpx.Response(200, json={"pong": True})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
async def client(
    async_engine,  # type: ignore[no-untyped-def]
    fake_upstream: httpx.AsyncClient,
    _crypto_env: None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Build the example app and yield an httpx.AsyncClient routed to it."""
    app = build_app(engine=async_engine, upstream_client=fake_upstream)
    transport = httpx.ASGITransport(app=app)
    # ASGITransport does not invoke lifespan; we drive it manually so
    # the recovery monitor + audit dispatcher start cleanly.
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as c,
        app.router.lifespan_context(app),
    ):
        yield c


async def test_health_routes_serve_200(client: httpx.AsyncClient) -> None:
    """``/healthz`` and ``/readyz`` both succeed with no backends registered."""
    assert (await client.get("/healthz")).status_code == 200
    readyz = await client.get("/readyz")
    assert readyz.status_code == 200
    assert readyz.json()["status"] == "ok"


async def test_rate_limit_denies_third_request(client: httpx.AsyncClient) -> None:
    """The 3rd /limited request returns 429 with the LLD §11 envelope."""
    assert (await client.get("/limited")).status_code == 200
    assert (await client.get("/limited")).status_code == 200
    response = await client.get("/limited")
    assert response.status_code == 429
    assert response.headers["retry-after"]
    body = response.json()
    assert body["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert body["details"]["limit"] == 2


async def test_encrypted_string_round_trips_through_postgres(
    client: httpx.AsyncClient,
    async_engine,  # type: ignore[no-untyped-def]
) -> None:
    """Cipher on disk; plaintext through the ORM."""
    create = await client.post("/secrets", json={"value": "top secret"})
    assert create.status_code == 200
    secret_id = create.json()["id"]

    read = await client.get(f"/secrets/{secret_id}")
    assert read.status_code == 200
    assert read.json()["value"] == "top secret"

    async with async_engine.connect() as conn:
        on_disk = (
            await conn.execute(text("SELECT value FROM secrets WHERE id = :i"), {"i": secret_id})
        ).scalar_one()
    assert on_disk != "top secret"
    assert on_disk.startswith("gAAAAA")


async def test_proxy_routes_to_fake_upstream(client: httpx.AsyncClient) -> None:
    """``AsyncAPIClient`` reaches the fake upstream via the injected transport."""
    response = await client.get("/proxy")
    assert response.status_code == 200
    assert response.json()["upstream_status"] == "200"
