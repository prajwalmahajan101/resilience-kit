"""Property-based tests for the breaker state machine — #D4.

Drives :class:`InMemoryAsyncBreaker` through randomised action sequences with
Hypothesis and asserts the LLD §4 invariants hold under every interleaving:

* excluded exceptions never cause a state transition;
* ``fail_max`` consecutive failures from CLOSED ⇒ OPEN;
* past ``reset_timeout`` the next call is admitted (OPEN ⇒ HALF_OPEN);
* ``success_threshold`` successes in HALF_OPEN ⇒ CLOSED.

Time is driven by :class:`FakeClock` so no real waiting occurs. Each async
call is run via ``asyncio.run`` — which also exercises the #D2 cross-loop
lock-rebind fix, since the breaker instance is reused across loops.
"""

from __future__ import annotations

import asyncio
from typing import NoReturn

import pytest
from hypothesis import HealthCheck, settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from resilience_kit.circuit_breaker.base import BreakerConfig, BreakerState
from resilience_kit.circuit_breaker.memory_impl import InMemoryAsyncBreaker
from resilience_kit.exceptions import ServiceUnavailableError
from resilience_kit.testing.fakes import FakeClock

_FAIL_MAX = 3
_SUCCESS_THRESHOLD = 2
_RESET_TIMEOUT = 10.0


async def _ok() -> str:
    return "ok"


async def _boom() -> NoReturn:
    raise RuntimeError("downstream failure")


async def _bad_input() -> NoReturn:
    raise ValueError("caller error — excluded from breaker accounting")


def _call(breaker: InMemoryAsyncBreaker, coro_fn: object) -> object:
    """Run one breaker call in a fresh loop, swallowing expected raises."""

    async def _runner() -> object:
        return await breaker.call(coro_fn)  # type: ignore[arg-type]

    return asyncio.run(_runner())


def _state(breaker: InMemoryAsyncBreaker) -> BreakerState:
    return asyncio.run(breaker.state())


class BreakerMachine(RuleBasedStateMachine):
    """Randomised driver asserting the breaker never violates its contract."""

    def __init__(self) -> None:
        super().__init__()
        self.clock = FakeClock()
        self.breaker = InMemoryAsyncBreaker(
            name="prop",
            config=BreakerConfig(
                fail_max=_FAIL_MAX,
                success_threshold=_SUCCESS_THRESHOLD,
                reset_timeout=_RESET_TIMEOUT,
                excluded_exceptions=(ValueError,),
            ),
            clock=self.clock,
        )
        # Consecutive counted failures observed while CLOSED, for the
        # fail_max ⇒ OPEN property.
        self.closed_failures = 0

    @rule()
    def succeed(self) -> None:
        try:
            result = _call(self.breaker, _ok)
        except ServiceUnavailableError:
            return  # OPEN short-circuits — legal.
        assert result == "ok"
        self.closed_failures = 0

    @rule()
    def fail(self) -> None:
        before = _state(self.breaker)
        try:
            _call(self.breaker, _boom)
        except ServiceUnavailableError:
            return  # OPEN short-circuits before the call runs.
        except RuntimeError:
            pass  # counted failure propagated.
        if before is BreakerState.CLOSED:
            self.closed_failures += 1
            if self.closed_failures >= _FAIL_MAX:
                # Property: fail_max consecutive failures from CLOSED ⇒ OPEN.
                assert _state(self.breaker) is BreakerState.OPEN
                self.closed_failures = 0

    @rule()
    def excluded_never_transitions(self) -> None:
        # Property: an excluded exception never moves the state machine.
        before = _state(self.breaker)
        if before is BreakerState.OPEN:
            return  # OPEN would short-circuit before func runs.
        with pytest.raises(ValueError, match="caller error"):
            _call(self.breaker, _bad_input)
        assert _state(self.breaker) is before

    @rule()
    def advance_past_timeout(self) -> None:
        self.clock.tick(_RESET_TIMEOUT + 1.0)

    @rule()
    def recover_after_timeout(self) -> None:
        # Property: past reset_timeout, the next call is admitted (OPEN ⇒
        # HALF_OPEN) rather than short-circuited. No-op unless OPEN.
        if _state(self.breaker) is not BreakerState.OPEN:
            return
        self.clock.tick(_RESET_TIMEOUT + 1.0)
        result = _call(self.breaker, _ok)
        assert result == "ok"
        self.closed_failures = 0

    @invariant()
    def state_is_valid(self) -> None:
        assert _state(self.breaker) in set(BreakerState)


TestBreakerStateMachine = BreakerMachine.TestCase
# Loop-heavy (asyncio.run per action); keep example count reasonable but ≥ the
# audit's "≥100 examples" bar via max_examples on the underlying settings.
TestBreakerStateMachine.settings = settings(
    max_examples=100,
    stateful_step_count=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)


def test_fail_max_from_closed_opens() -> None:
    """Direct check: fail_max consecutive failures open a CLOSED breaker."""
    clock = FakeClock()
    breaker = InMemoryAsyncBreaker(
        name="direct",
        config=BreakerConfig(fail_max=_FAIL_MAX, reset_timeout=_RESET_TIMEOUT),
        clock=clock,
    )

    async def _drive() -> BreakerState:
        for _ in range(_FAIL_MAX):
            with pytest.raises(RuntimeError):
                await breaker.call(_boom)
        return await breaker.state()

    assert asyncio.run(_drive()) is BreakerState.OPEN


def test_half_open_closes_after_success_threshold() -> None:
    """HALF_OPEN ⇒ CLOSED after success_threshold consecutive successes."""
    clock = FakeClock()
    breaker = InMemoryAsyncBreaker(
        name="direct2",
        config=BreakerConfig(
            fail_max=_FAIL_MAX,
            success_threshold=_SUCCESS_THRESHOLD,
            reset_timeout=_RESET_TIMEOUT,
        ),
        clock=clock,
    )

    async def _drive() -> BreakerState:
        for _ in range(_FAIL_MAX):
            with pytest.raises(RuntimeError):
                await breaker.call(_boom)
        clock.tick(_RESET_TIMEOUT + 1.0)
        for _ in range(_SUCCESS_THRESHOLD):
            await breaker.call(_ok)
        return await breaker.state()

    assert asyncio.run(_drive()) is BreakerState.CLOSED
