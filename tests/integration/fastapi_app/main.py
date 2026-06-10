"""Minimal FastAPI app demonstrating the kit's M5 adapter end-to-end.

A reviewer should be able to copy this file into a fresh project,
``pip install resilience-kit[fastapi,redis,crypto,audit-postgres]``,
set ``RESILIENCE_REDIS_URL`` + ``RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY``,
and have working resilience.

Wired pieces:

* ``resilience_lifespan()`` — starts the recovery monitor, drains the
  audit dispatcher on shutdown.
* ``install_health_routes`` — ``/readyz`` and ``/healthz``.
* ``install_exception_handlers`` — every kit exception becomes the
  locked LLD §11 JSON envelope.
* ``install_middleware_stack`` — the recommended outer→inner stack.
* ``rate_limit(Scope.IP, "2/min")`` on ``/limited``.
* ``AsyncAPIClient("partner")`` behind ``/proxy`` (wrapped by
  ``@resilient`` automatically).
* ``Secret`` SQLAlchemy model with an ``EncryptedString`` column.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI
from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.ext.asyncio import async_sessionmaker

from resilience_kit.adapters.fastapi import (
    EncryptedString,
    install_exception_handlers,
    install_health_routes,
    install_middleware_stack,
    rate_limit,
    resilience_lifespan,
)
from resilience_kit.http_client import AsyncAPIClient
from resilience_kit.throttle.scopes import Scope

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncEngine


METADATA = MetaData()
SECRETS = Table(
    "secrets",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("value", EncryptedString(512), nullable=False),
)


def build_app(
    *,
    engine: AsyncEngine,
    upstream_client: httpx.AsyncClient,
) -> FastAPI:
    """Construct the example app with the adapter wired in.

    Args:
        engine: An async SQLAlchemy engine connected to the test
            Postgres container.
        upstream_client: A pre-built ``httpx.AsyncClient`` for the fake
            upstream. In production an adopter would let
            :class:`AsyncAPIClient` build its own; here we inject one
            so the integration test can route to an in-process
            transport.

    Returns:
        The configured :class:`FastAPI` instance.
    """
    app = FastAPI(lifespan=resilience_lifespan())
    install_health_routes(app)
    install_exception_handlers(app)
    install_middleware_stack(app)

    api_client = AsyncAPIClient(
        "partner",
        client=upstream_client,
        check_ssrf=False,
    )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    @app.get("/limited", dependencies=[Depends(rate_limit(Scope.IP, "2/min"))])
    async def limited() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/proxy")
    async def proxy() -> dict[str, str]:
        response = await api_client.get("http://upstream.test/ping")
        return {"upstream_status": str(response.status_code)}

    @app.post("/secrets")
    async def create_secret(payload: dict[str, str]) -> dict[str, int]:
        async with sessionmaker() as session, session.begin():
            result = await session.execute(
                SECRETS.insert().values(value=payload["value"]).returning(SECRETS.c.id),
            )
            new_id = result.scalar_one()
        return {"id": new_id}

    @app.get("/secrets/{secret_id}")
    async def read_secret(secret_id: int) -> dict[str, str]:
        async with sessionmaker() as session:
            row = (
                await session.execute(
                    SECRETS.select().where(SECRETS.c.id == secret_id),
                )
            ).one()
        return {"value": row.value}

    return app
