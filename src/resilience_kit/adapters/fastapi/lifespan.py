"""FastAPI lifespan + ``/readyz`` / ``/healthz`` route installer.

The kit's :class:`~resilience_kit.recovery.RecoveryMonitor` and audit
:class:`~resilience_kit.audit.dispatch.FireAndForgetDispatcher` both
expect an event loop they can attach to. FastAPI's
``lifespan=`` parameter (PEP 525 async context manager) is exactly that
attachment point: it runs after the loop is up, before the first
request, and again on graceful shutdown.

This module exposes two helpers:

* :func:`resilience_lifespan` — factory that returns a lifespan callable
  starting the recovery monitor on enter and draining the audit
  dispatcher + stopping the monitor on exit. Accepts an optional inner
  lifespan so an app can chain its own startup hooks without giving up
  the kit's lifecycle management.
* :func:`install_health_routes` — mounts ``GET /healthz`` (liveness;
  always 200) and ``GET /readyz`` (readiness; reads
  :func:`~resilience_kit.health.health_snapshot`).

Two helpers rather than one because FastAPI only accepts a lifespan at
``FastAPI(lifespan=...)`` construction time, but routes can be added
later. Splitting them lets adopters wire each at the natural moment.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from resilience_kit.audit.factory import get_dispatcher
from resilience_kit.exceptions import MissingExtraError
from resilience_kit.health import health_snapshot
from resilience_kit.recovery import monitor

try:
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("fastapi", "prajwal-resilience-kit[fastapi]") from exc

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

    from fastapi import FastAPI

    LifespanFactory = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def resilience_lifespan(
    inner: LifespanFactory | None = None,
) -> LifespanFactory:
    """Build a FastAPI lifespan that owns the kit's background workers.

    Enter:

    1. Start the process-wide :data:`~resilience_kit.recovery.monitor`.
    2. Enter ``inner(app)`` if provided so the app's own startup hooks
       run after the kit's.

    Exit (in reverse order):

    1. Exit the inner lifespan, propagating any exception.
    2. Drain + close the audit dispatcher (``await aclose(drain_timeout=5.0)``).
    3. Stop the recovery monitor (``await monitor.stop()``).

    Args:
        inner: Optional user-supplied lifespan factory. Use this to
            compose the kit's lifecycle with app-specific startup /
            shutdown work without losing either side.

    Returns:
        A lifespan callable suitable for ``FastAPI(lifespan=...)``.

    Example:
        >>> from fastapi import FastAPI
        >>> from resilience_kit.adapters.fastapi import resilience_lifespan
        >>> app = FastAPI(lifespan=resilience_lifespan())
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        monitor.start()
        try:
            if inner is not None:
                async with inner(app):
                    yield
            else:
                yield
        finally:
            # Drain audit before stopping the monitor so any audit events
            # produced during the inner shutdown are flushed.
            await get_dispatcher().aclose(drain_timeout=5.0)
            await monitor.stop()

    return _lifespan


def install_health_routes(
    app: FastAPI,
    *,
    readyz_path: str = "/readyz",
    healthz_path: str = "/healthz",
    probe_timeout: float = 1.0,
) -> None:
    """Mount ``/readyz`` and ``/healthz`` on ``app``.

    ``/healthz`` is a liveness probe — it returns 200 as long as the
    process can serve a request. ``/readyz`` reads
    :func:`~resilience_kit.health.health_snapshot` and propagates its
    ``http_status`` (200 / 503) and per-backend snapshot list. Matches
    Kubernetes probe conventions.

    Args:
        app: Target FastAPI application.
        readyz_path: Override the readyz path (defaults to ``/readyz``).
        healthz_path: Override the healthz path.
        probe_timeout: Per-backend probe deadline forwarded to
            :func:`health_snapshot`.
    """

    @app.get(healthz_path, include_in_schema=False)
    async def _healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get(readyz_path, include_in_schema=False)
    async def _readyz() -> JSONResponse:
        aggregate = await health_snapshot(probe_timeout=probe_timeout)
        return JSONResponse(
            {
                "status": aggregate.status.value,
                "snapshots": [
                    {
                        "backend": s.backend,
                        "healthy": s.healthy,
                        "detail": s.detail,
                    }
                    for s in aggregate.snapshots
                ],
            },
            status_code=aggregate.http_status,
        )


__all__ = ["install_health_routes", "resilience_lifespan"]
