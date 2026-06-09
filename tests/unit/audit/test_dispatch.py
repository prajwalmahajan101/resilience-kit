"""Unit tests for :mod:`resilience_kit.audit.dispatch`."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from resilience_kit.audit.backends.base import AuditEvent
from resilience_kit.audit.dispatch import (
    AuditDispatcher,
    FireAndForgetDispatcher,
    InlineDispatcher,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def _event(**overrides: object) -> AuditEvent:
    base = {
        "direction": "outbound",
        "service": "partner",
        "method": "GET",
        "path": "/v1/x",
        "outcome": "success",
        "latency_ms": 1.0,
        "payload": {"password": "p", "ok": "v"},
    }
    base.update(overrides)
    return AuditEvent(**base)  # type: ignore[arg-type]


class _CollectingBackend:
    """Backend that records every batch it writes."""

    def __init__(self) -> None:
        self.batches: list[list[AuditEvent]] = []

    async def write_many(self, events: Sequence[AuditEvent]) -> None:
        self.batches.append(list(events))

    async def health_check(self) -> bool:
        return True


class _FlakyBackend:
    """Backend that raises ``fail_attempts`` times before succeeding."""

    def __init__(self, *, fail_attempts: int) -> None:
        self._fail_attempts = fail_attempts
        self.attempts = 0
        self.last_batch: list[AuditEvent] = []

    async def write_many(self, events: Sequence[AuditEvent]) -> None:
        self.attempts += 1
        if self.attempts <= self._fail_attempts:
            msg = f"attempt {self.attempts} fails"
            raise RuntimeError(msg)
        self.last_batch = list(events)

    async def health_check(self) -> bool:
        return True


class _AlwaysFailingBackend:
    """Backend that never succeeds."""

    def __init__(self) -> None:
        self.attempts = 0

    async def write_many(self, events: Sequence[AuditEvent]) -> None:
        self.attempts += 1
        msg = "broken"
        raise RuntimeError(msg)

    async def health_check(self) -> bool:
        return False


async def _wait_until(predicate: object, *, max_seconds: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + max_seconds
    while asyncio.get_running_loop().time() < deadline:
        if predicate():  # type: ignore[operator]
            return
        await asyncio.sleep(0.01)
    msg = "predicate did not become truthy"
    raise AssertionError(msg)


# --- InlineDispatcher --------------------------------------------------------


@pytest.mark.asyncio
async def test_inline_dispatcher_sanitises_before_writing() -> None:
    """The dispatcher redacts before handing events to the backend."""
    backend = _CollectingBackend()
    dispatcher = InlineDispatcher(backend)
    dispatcher.submit(_event())
    await dispatcher.flush()
    assert backend.batches
    assert backend.batches[0][0].payload["password"] == "[REDACTED]"
    assert backend.batches[0][0].payload["ok"] == "v"


@pytest.mark.asyncio
async def test_inline_dispatcher_propagates_backend_errors() -> None:
    """Backend errors surface from ``flush`` so tests can assert on them."""
    backend = _AlwaysFailingBackend()
    dispatcher = InlineDispatcher(backend)
    dispatcher.submit(_event())
    with pytest.raises(RuntimeError, match="broken"):
        await dispatcher.flush()


def test_inline_dispatcher_implements_protocol() -> None:
    """Inline dispatcher satisfies the AuditDispatcher protocol."""
    assert isinstance(InlineDispatcher(_CollectingBackend()), AuditDispatcher)


# --- FireAndForgetDispatcher ------------------------------------------------


@pytest.mark.asyncio
async def test_fire_and_forget_writes_and_sanitises() -> None:
    """Events submitted asynchronously reach the backend, sanitised."""
    backend = _CollectingBackend()
    dispatcher = FireAndForgetDispatcher(backend, batch_interval_ms=10)
    dispatcher.submit(_event())
    await _wait_until(lambda: bool(backend.batches))
    assert backend.batches[0][0].payload["password"] == "[REDACTED]"
    await dispatcher.aclose()


@pytest.mark.asyncio
async def test_fire_and_forget_retries_then_succeeds() -> None:
    """Two transient failures, third attempt succeeds — events land."""
    backend = _FlakyBackend(fail_attempts=2)
    dispatcher = FireAndForgetDispatcher(backend, batch_interval_ms=10)
    dispatcher.submit(_event())
    await _wait_until(lambda: bool(backend.last_batch), max_seconds=3.0)
    assert backend.attempts == 3
    await dispatcher.aclose()


@pytest.mark.asyncio
async def test_fire_and_forget_falls_back_to_logging() -> None:
    """All retries exhausted → fallback backend receives the batch."""
    backend = _AlwaysFailingBackend()
    fallback = _CollectingBackend()
    dispatcher = FireAndForgetDispatcher(
        backend,
        fallback=fallback,
        batch_interval_ms=10,
    )
    dispatcher.submit(_event())
    await _wait_until(lambda: bool(fallback.batches), max_seconds=3.0)
    assert backend.attempts == 3
    assert fallback.batches[0][0].payload["password"] == "[REDACTED]"
    await dispatcher.aclose()


def test_fire_and_forget_implements_protocol() -> None:
    """Production dispatcher satisfies the AuditDispatcher protocol."""
    dispatcher = FireAndForgetDispatcher(_CollectingBackend())
    assert isinstance(dispatcher, AuditDispatcher)
