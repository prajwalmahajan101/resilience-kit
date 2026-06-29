"""ASGI-compatibility tests for the Django sync→async bridge (#C6).

Under ASGI Django the DRF throttle's ``allow_request`` runs while an event
loop is already running; the v0.1 ``asyncio.run(...)`` bridge raised
``RuntimeError`` there. The fix routes the coroutine onto the adapter's
persistent daemon loop via ``run_coroutine_threadsafe``, which works from
both sync (WSGI) and running-loop (ASGI) contexts. These tests pin both.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("django")
pytest.importorskip("rest_framework")

from resilience_kit.adapters.django import apps as django_apps
from resilience_kit.adapters.django._bridge import run_on_kit_loop
from resilience_kit.testing import reset_all_singletons
from resilience_kit.throttle.base import Rate
from resilience_kit.throttle.provider import get_throttle


@pytest.fixture(autouse=True)
def _stop_monitor_thread() -> None:
    """Tear the daemon monitor thread down after each test for isolation."""
    yield
    django_apps._shutdown_monitor_thread()
    reset_all_singletons()


async def _check_once() -> bool:
    decision = await get_throttle().check("c6-test-key", Rate.parse("60/min"))
    return decision.allowed


def test_asyncio_run_raises_inside_running_loop() -> None:
    """Document the bug the bridge fixes: asyncio.run() 500s under ASGI."""

    async def _inner() -> None:
        # We are inside a running loop here — exactly the ASGI situation.
        coro = _check_once()
        try:
            with pytest.raises(RuntimeError, match="cannot be called from a running"):
                asyncio.run(coro)
        finally:
            coro.close()  # asyncio.run raised before awaiting; close to silence the warning.

    asyncio.run(_inner())


def test_bridge_runs_throttle_check_inside_running_loop() -> None:
    """The bridge resolves a throttle check from within a running loop."""

    async def _inner() -> bool:
        # Blocking on the daemon loop from inside this loop is the ASGI path.
        return run_on_kit_loop(_check_once())

    assert asyncio.run(_inner()) is True


def test_bridge_runs_from_sync_context() -> None:
    """The bridge also works from plain sync code (the WSGI path)."""
    assert run_on_kit_loop(_check_once()) is True
