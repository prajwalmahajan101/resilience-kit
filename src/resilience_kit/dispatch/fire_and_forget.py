"""Bounded fire-and-forget queue + background worker (LLD §7).

The :class:`FireAndForget` worker is the building block shared by
:mod:`resilience_kit.audit.dispatch` and :mod:`resilience_kit.tasks.queue`.
Callers push events with :meth:`submit`; a background asyncio task drains
the queue in batches and hands each batch to a caller-supplied async
``flush`` callback.

Guarantees (LLD §7):

* **Submit is non-blocking.** Callers never await backend I/O. A full
  queue drops events according to the configured :class:`OverflowPolicy`
  and increments ``<metric_prefix>.dropped`` so the loss is visible.
* **Batches are bounded.** ``batch_max`` events per call to ``flush`` and
  at most ``batch_interval_ms`` of wait between flushes.
* **Graceful drain.** :meth:`aclose` waits for both queued and in-flight
  events to flush via :meth:`asyncio.Queue.join`, or aborts after
  ``timeout``; remaining events go to the dropped metric.
* **ContextVar isolation.** The worker is spawned in a fresh
  :func:`contextvars.copy_context` so the request that submitted an
  event cannot leak its pin into another's flush.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Generic, TypeVar

from resilience_kit.metrics import get_metrics

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

_logger = logging.getLogger(__name__)

T = TypeVar("T")


class OverflowPolicy(StrEnum):
    """How the queue behaves when :meth:`FireAndForget.submit` finds it full."""

    DROP_NEWEST = "drop_newest"
    """Refuse the incoming event; counter is bumped."""

    DROP_OLDEST = "drop_oldest"
    """Discard the oldest queued event to make room for the new one."""


class FireAndForget(Generic[T]):
    """Bounded queue with a background batch-flushing worker.

    The worker is started lazily by the first :meth:`submit` so the
    object can be instantiated outside a running event loop.
    """

    def __init__(
        self,
        flush: Callable[[Sequence[T]], Awaitable[None]],
        *,
        queue_size: int = 10_000,
        batch_max: int = 100,
        batch_interval_ms: int = 50,
        overflow: OverflowPolicy = OverflowPolicy.DROP_NEWEST,
        metric_prefix: str = "dispatch",
        name: str = "fire_and_forget",
    ) -> None:
        """Configure the worker.

        Args:
            flush: Async callable invoked with a batch of events. Errors
                raised by ``flush`` are logged and counted via
                ``<metric_prefix>.flush_failed``; they never propagate
                to submitters.
            queue_size: Maximum events held before overflow kicks in.
            batch_max: Maximum events handed to ``flush`` per call.
            batch_interval_ms: Maximum wait between batch flushes.
            overflow: Behaviour when the queue is full.
            metric_prefix: Dotted prefix for the worker's emitted
                metrics (``submitted`` / ``dropped`` / ``flushed`` /
                ``flush_failed``).
            name: Human-readable identifier used in log lines and tags.
        """
        self._flush = flush
        self._queue_size = queue_size
        self._batch_max = batch_max
        self._batch_interval_s = batch_interval_ms / 1000
        self._overflow = overflow
        self._metric_prefix = metric_prefix
        self._name = name

        self._queue: asyncio.Queue[T] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def started(self) -> bool:
        """Whether the background worker is alive."""
        return self._worker is not None and not self._worker.done()

    def submit(self, event: T) -> bool:
        """Enqueue ``event``; returns ``True`` on accept, ``False`` on drop.

        Starts the worker on the first call (must be called from inside
        a running event loop).

        Args:
            event: The event to enqueue. Opaque to the dispatcher.

        Returns:
            ``True`` when the event was queued, ``False`` when overflow
            policy caused it (or an older event) to be dropped.

        Raises:
            RuntimeError: The worker has been closed.
        """
        if self._closed:
            msg = f"FireAndForget '{self._name}' is closed."
            raise RuntimeError(msg)
        self._ensure_started()
        assert self._queue is not None
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            return self._handle_overflow(event)
        get_metrics().incr(
            f"{self._metric_prefix}.submitted",
            tags={"name": self._name},
        )
        return True

    def _ensure_started(self) -> None:
        """Allocate the queue + spawn the worker if not already running."""
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._queue_size)
        if self.started:
            return
        ctx = contextvars.copy_context()
        loop = asyncio.get_running_loop()
        self._worker = loop.create_task(
            self._run(),
            name=f"fire_and_forget:{self._name}",
            context=ctx,
        )

    def _handle_overflow(self, event: T) -> bool:
        """Apply :class:`OverflowPolicy` and bump the dropped counter."""
        assert self._queue is not None
        get_metrics().incr(
            f"{self._metric_prefix}.dropped",
            tags={"name": self._name},
        )
        if self._overflow is OverflowPolicy.DROP_OLDEST:
            with contextlib.suppress(asyncio.QueueEmpty):
                # Counts the displaced event as a completed unit of work
                # so queue.join() in aclose() does not deadlock waiting
                # for it to be flushed.
                self._queue.get_nowait()
                self._queue.task_done()
            self._queue.put_nowait(event)
            return True
        return False

    async def _run(self) -> None:
        """Drain the queue in batches, calling ``flush`` per batch."""
        assert self._queue is not None
        while True:
            try:
                first = await self._queue.get()
            except asyncio.CancelledError:
                return
            batch: list[T] = [first]
            await self._fill_batch(batch)
            await self._flush_batch(batch)
            # Mark every item in this batch done so queue.join() in
            # aclose() resolves once all pending and in-flight work is
            # complete.
            for _ in batch:
                self._queue.task_done()

    async def _fill_batch(self, batch: list[T]) -> None:
        """Wait up to ``batch_interval_s`` for more events, up to ``batch_max``."""
        assert self._queue is not None
        deadline = asyncio.get_running_loop().time() + self._batch_interval_s
        while len(batch) < self._batch_max:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except TimeoutError:
                return
            batch.append(event)

    async def _flush_batch(self, batch: list[T]) -> None:
        """Hand a batch to ``flush``; swallow + meter errors."""
        try:
            await self._flush(batch)
        except Exception:
            _logger.exception(
                "FireAndForget '%s' flush failed; dropping %d events.",
                self._name,
                len(batch),
            )
            get_metrics().incr(
                f"{self._metric_prefix}.flush_failed",
                value=len(batch),
                tags={"name": self._name},
            )
            return
        get_metrics().incr(
            f"{self._metric_prefix}.flushed",
            value=len(batch),
            tags={"name": self._name},
        )

    async def aclose(self, *, drain_timeout: float = 5.0) -> None:
        """Drain remaining events, then stop the worker.

        Args:
            drain_timeout: Maximum seconds to wait for queued + in-flight
                events to flush. Events still pending when the timeout
                elapses are counted as dropped.
        """
        if self._closed:
            return
        self._closed = True
        if self._queue is None or self._worker is None:
            return
        try:
            async with asyncio.timeout(drain_timeout):
                await self._queue.join()
        except TimeoutError:
            remaining = self._queue.qsize()
            if remaining:
                get_metrics().incr(
                    f"{self._metric_prefix}.dropped",
                    value=remaining,
                    tags={"name": self._name, "reason": "shutdown_timeout"},
                )
        self._worker.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._worker


__all__ = ["FireAndForget", "OverflowPolicy"]
