"""Sync → kit-loop bridge for the Django adapter (#C6, ADR-0011 amended).

Django is sync-first. DRF throttle classes are sync (`allow_request`),
but the kit's throttle is async. v0.1 bridged each call with
``asyncio.run(...)``, which raises ``RuntimeError: asyncio.run() cannot
be called from a running event loop`` the moment the project is served
under ASGI (Daphne / Uvicorn) — so every kit-throttled DRF route 500'd
on ASGI deployments.

This module routes the coroutine onto the adapter's **persistent**
daemon-thread loop (owned by ``apps.py`` for the recovery monitor) via
:func:`asyncio.run_coroutine_threadsafe`, blocking the calling thread for
the result. That works whether or not the caller is inside a running
loop, and because every call shares the one long-lived loop, async
primitives bound to it never rebind across calls.

ADR-0011 originally *rejected* ``run_coroutine_threadsafe`` here on
latency / state-coupling grounds; #C6 reverses that, because ASGI
correctness outweighs the sub-millisecond scheduling overhead and the
shared persistent loop is in fact what removes the cross-loop hazard.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar

from resilience_kit.adapters.django.apps import get_kit_loop

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from typing import Any

T = TypeVar("T")

#: Upper bound on how long a bridged call may block the calling thread.
#: A throttle check is one Redis round-trip; 10 s is generous headroom
#: that still fails fast if the loop is wedged.
_BRIDGE_TIMEOUT_SECONDS = 10.0


def run_on_kit_loop(
    coro: Coroutine[Any, Any, T],
    *,
    timeout: float = _BRIDGE_TIMEOUT_SECONDS,
) -> T:
    """Run ``coro`` to completion on the adapter's persistent daemon loop.

    Args:
        coro: An un-awaited coroutine (e.g. ``throttle.check(...)``).
        timeout: Seconds to block the calling thread before giving up.

    Returns:
        The coroutine's result.

    Raises:
        concurrent.futures.TimeoutError: The loop did not finish in time.
        Exception: Anything the coroutine itself raises is re-raised here.
    """
    loop = get_kit_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)


__all__ = ["run_on_kit_loop"]
