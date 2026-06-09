"""Recovery monitor — registration, probe, warm-hook semantics."""

from __future__ import annotations

import pytest

from resilience_kit.circuit_breaker.base import HealthSnapshot
from resilience_kit.recovery import (
    RecoveryMonitor,
    attempt_recover_all,
    register_for_recovery,
    register_warm_hook,
    registered_backends,
    reset_recovery_state,
    unregister_for_recovery,
)


class _FakeBackend:
    """Backend whose ``try_recover`` returns whatever the test sets."""

    def __init__(self, *, name: str = "fake", recover_returns: bool = False) -> None:
        self.name = name
        self.recover_returns = recover_returns
        self.recover_called = 0

    async def try_recover(self) -> bool:
        self.recover_called += 1
        return self.recover_returns

    async def health_check(self) -> HealthSnapshot:
        return HealthSnapshot(healthy=False, backend="fake")


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_recovery_state()


def test_register_and_unregister() -> None:
    b = _FakeBackend()
    register_for_recovery(b)
    assert b in registered_backends()
    unregister_for_recovery(b)
    assert b not in registered_backends()


def test_register_is_idempotent() -> None:
    b = _FakeBackend()
    register_for_recovery(b)
    register_for_recovery(b)
    assert registered_backends().count(b) == 1


async def test_attempt_recover_returns_count() -> None:
    a = _FakeBackend(name="a", recover_returns=True)
    b = _FakeBackend(name="b", recover_returns=False)
    register_for_recovery(a)
    register_for_recovery(b)
    n = await attempt_recover_all()
    assert n == 1
    assert a.recover_called == 1
    assert b.recover_called == 1


async def test_warm_hooks_fire_on_recovery() -> None:
    fired = 0

    async def hook() -> None:
        nonlocal fired
        fired += 1

    register_warm_hook(hook)
    a = _FakeBackend(recover_returns=True)
    register_for_recovery(a)
    await attempt_recover_all()
    assert fired == 1


async def test_warm_hooks_do_not_fire_when_nothing_recovered() -> None:
    fired = 0

    async def hook() -> None:
        nonlocal fired
        fired += 1

    register_warm_hook(hook)
    a = _FakeBackend(recover_returns=False)
    register_for_recovery(a)
    await attempt_recover_all()
    assert fired == 0


async def test_monitor_start_stop_idempotent() -> None:
    m = RecoveryMonitor()
    m.start()
    m.start()  # idempotent
    await m.stop(timeout=1.0)
    await m.stop(timeout=1.0)  # idempotent
