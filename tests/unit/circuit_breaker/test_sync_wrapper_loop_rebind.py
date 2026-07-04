"""Sync ``@circuit_breaker`` across event loops — #D2.

The sync wrapper runs a fresh ``asyncio.run`` per call, so a breaker instance
is driven by a new loop each time. Its internal ``asyncio.Lock`` must not stay
bound to the first (now-dead) loop, or the second call raises
``RuntimeError: <Lock ...> is bound to a different event loop``.
"""

from __future__ import annotations

import asyncio

from resilience_kit.circuit_breaker.memory_impl import InMemoryAsyncBreaker
from resilience_kit.decorators import circuit_breaker


def test_sync_decorated_call_twice_no_loop_rebind_error() -> None:
    """Two consecutive sync calls succeed without a cross-loop RuntimeError."""
    calls = {"n": 0}

    @circuit_breaker("svc-d2")
    def work() -> int:
        calls["n"] += 1
        return calls["n"]

    first = work()
    second = work()

    assert first == 1
    assert second == 2


def test_breaker_lock_rebinds_across_loops() -> None:
    """The same breaker instance is usable from two independent loops."""
    breaker = InMemoryAsyncBreaker(name="svc-d2-direct")

    async def _one() -> str:
        return await breaker.call(_ok)

    async def _ok() -> str:
        return "ok"

    # Two separate event loops, same breaker instance — the second would
    # raise "bound to a different event loop" without the lock-factory fix.
    assert asyncio.run(_one()) == "ok"
    assert asyncio.run(_one()) == "ok"
