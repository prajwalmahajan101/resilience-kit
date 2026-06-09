"""Unit tests for :mod:`resilience_kit.tasks`."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from resilience_kit.tasks import get_queue, register, reset_tasks, submit
from resilience_kit.tasks.registry import reset_registry

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    reset_registry()
    reset_tasks()
    yield
    reset_registry()
    reset_tasks()


async def _wait_until(predicate: object, *, max_seconds: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + max_seconds
    while asyncio.get_running_loop().time() < deadline:
        if predicate():  # type: ignore[operator]
            return
        await asyncio.sleep(0.01)
    msg = "predicate did not become truthy"
    raise AssertionError(msg)


@pytest.mark.asyncio
async def test_registered_task_runs_when_submitted() -> None:
    """The worker dispatches to the registered handler."""
    results: list[int] = []

    @register("double")
    async def double(value: int) -> None:
        results.append(value * 2)

    assert submit("double", 21) is True
    await _wait_until(lambda: bool(results))
    assert results == [42]
    await get_queue().aclose()


@pytest.mark.asyncio
async def test_submit_unknown_task_raises_keyerror() -> None:
    """Missing handler raises at submit time, not at worker time."""
    with pytest.raises(KeyError, match="No task handler registered"):
        submit("does-not-exist", 1)


@pytest.mark.asyncio
async def test_handler_failures_are_swallowed_and_metered() -> None:
    """A raise inside a task does not break the worker."""
    success: list[int] = []

    @register("ok")
    async def ok(value: int) -> None:
        success.append(value)

    @register("bad")
    async def bad() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    submit("bad")
    submit("ok", 7)
    # The worker keeps running after the failure; the ok task still runs.
    await _wait_until(lambda: success == [7])
    await get_queue().aclose()


def test_double_register_with_different_callable_raises() -> None:
    """Re-registering the same name with a new handler is an error."""

    @register("send")
    async def first() -> None:
        return None

    with pytest.raises(ValueError, match="already registered"):

        @register("send")
        async def second() -> None:
            return None


@pytest.mark.asyncio
async def test_kwargs_are_forwarded() -> None:
    """Keyword arguments make it through the queue unchanged."""
    captured: dict[str, object] = {}

    @register("kwfn")
    async def fn(**kwargs: object) -> None:
        captured.update(kwargs)

    submit("kwfn", to="alice", body="hi")
    await _wait_until(lambda: bool(captured))
    assert captured == {"to": "alice", "body": "hi"}
    await get_queue().aclose()
