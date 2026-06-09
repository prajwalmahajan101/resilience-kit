"""Unit tests for :mod:`resilience_kit.dispatch.fire_and_forget`."""

from __future__ import annotations

import asyncio

import pytest

from resilience_kit.dispatch.fire_and_forget import FireAndForget, OverflowPolicy


async def _wait_until(predicate: object, *, max_seconds: float = 2.0) -> None:
    """Poll ``predicate()`` every 10ms until truthy or timeout."""
    deadline = asyncio.get_running_loop().time() + max_seconds
    while asyncio.get_running_loop().time() < deadline:
        if predicate():  # type: ignore[operator]
            return
        await asyncio.sleep(0.01)
    msg = "predicate did not become truthy"
    raise AssertionError(msg)


@pytest.mark.asyncio
async def test_submit_and_flush_single_event() -> None:
    """Submitted event reaches flush in a single batch."""
    flushed: list[list[int]] = []

    async def flush(batch: list[int]) -> None:  # type: ignore[type-arg]
        flushed.append(list(batch))

    worker: FireAndForget[int] = FireAndForget(
        flush,  # type: ignore[arg-type]
        batch_interval_ms=10,
    )
    assert worker.submit(1) is True
    await _wait_until(lambda: flushed)
    assert flushed == [[1]]
    await worker.aclose()


@pytest.mark.asyncio
async def test_batching_up_to_batch_max() -> None:
    """A burst of events is delivered in batches capped at ``batch_max``."""
    flushed: list[int] = []

    async def flush(batch: list[int]) -> None:  # type: ignore[type-arg]
        flushed.extend(batch)

    worker: FireAndForget[int] = FireAndForget(
        flush,  # type: ignore[arg-type]
        batch_max=3,
        batch_interval_ms=20,
    )
    for i in range(7):
        assert worker.submit(i) is True
    await _wait_until(lambda: len(flushed) == 7)
    assert flushed == list(range(7))
    await worker.aclose()


@pytest.mark.asyncio
async def test_overflow_drop_newest_returns_false() -> None:
    """``DROP_NEWEST`` returns ``False`` from submit when the queue is full."""
    block = asyncio.Event()
    seen: list[int] = []

    async def flush(batch: list[int]) -> None:  # type: ignore[type-arg]
        await block.wait()  # hold the worker so the queue fills.
        seen.extend(batch)

    worker: FireAndForget[int] = FireAndForget(
        flush,  # type: ignore[arg-type]
        queue_size=2,
        batch_max=1,
        batch_interval_ms=5,
        overflow=OverflowPolicy.DROP_NEWEST,
    )
    # First submit gets pulled into the in-flight batch (worker hangs on block).
    assert worker.submit(0) is True
    # Give the worker a tick to dequeue event 0 so the queue is empty again.
    await asyncio.sleep(0.02)
    # Fill the queue (size=2).
    assert worker.submit(1) is True
    assert worker.submit(2) is True
    # Third submit overflows.
    assert worker.submit(3) is False
    block.set()
    await _wait_until(lambda: len(seen) >= 3)
    assert 3 not in seen
    await worker.aclose()


@pytest.mark.asyncio
async def test_overflow_drop_oldest_keeps_newest() -> None:
    """``DROP_OLDEST`` discards the oldest queued event to make room."""
    block = asyncio.Event()
    seen: list[int] = []

    async def flush(batch: list[int]) -> None:  # type: ignore[type-arg]
        await block.wait()
        seen.extend(batch)

    worker: FireAndForget[int] = FireAndForget(
        flush,  # type: ignore[arg-type]
        queue_size=2,
        batch_max=1,
        batch_interval_ms=5,
        overflow=OverflowPolicy.DROP_OLDEST,
    )
    assert worker.submit(0) is True
    await asyncio.sleep(0.02)
    assert worker.submit(1) is True
    assert worker.submit(2) is True
    # Drops 1 to make room for 3.
    assert worker.submit(3) is True
    block.set()
    await _wait_until(lambda: len(seen) >= 3)
    assert 1 not in seen
    assert 3 in seen
    await worker.aclose()


@pytest.mark.asyncio
async def test_flush_failure_is_swallowed_and_metered() -> None:
    """A raising flush does not crash the worker; counter is bumped."""
    calls = 0

    async def flush(batch: list[int]) -> None:  # type: ignore[type-arg, ARG001]
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "boom"
            raise RuntimeError(msg)

    worker: FireAndForget[int] = FireAndForget(
        flush,  # type: ignore[arg-type]
        batch_interval_ms=10,
    )
    worker.submit(1)
    await _wait_until(lambda: calls >= 1)
    # Second submit must still be handled — worker survived the raise.
    worker.submit(2)
    await _wait_until(lambda: calls >= 2)
    await worker.aclose()


@pytest.mark.asyncio
async def test_aclose_drains_remaining_events() -> None:
    """``aclose`` waits for queued events to flush before cancelling the worker."""
    seen: list[int] = []

    async def flush(batch: list[int]) -> None:  # type: ignore[type-arg]
        seen.extend(batch)

    worker: FireAndForget[int] = FireAndForget(
        flush,  # type: ignore[arg-type]
        batch_interval_ms=10,
    )
    for i in range(5):
        worker.submit(i)
    await worker.aclose(drain_timeout=2.0)
    assert sorted(seen) == list(range(5))


@pytest.mark.asyncio
async def test_submit_after_close_raises() -> None:
    """Closed worker rejects new submits."""

    async def flush(batch: list[int]) -> None:  # type: ignore[type-arg, ARG001]
        return

    worker: FireAndForget[int] = FireAndForget(flush, batch_interval_ms=5)  # type: ignore[arg-type]
    worker.submit(1)
    await worker.aclose()
    with pytest.raises(RuntimeError, match="is closed"):
        worker.submit(2)
