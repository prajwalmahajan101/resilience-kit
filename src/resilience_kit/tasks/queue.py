"""Fire-and-forget task queue built on :class:`dispatch.FireAndForget`.

A submitted task is a tuple of ``(name, args, kwargs)``. The worker
looks up the handler in :mod:`resilience_kit.tasks.registry`, awaits
it, and metrics any failure via ``tasks.failed`` so visibility does
not depend on application logging.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from resilience_kit.dispatch.fire_and_forget import FireAndForget
from resilience_kit.metrics import get_metrics
from resilience_kit.tasks.registry import get_handler

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TaskCall:
    """One queued task invocation."""

    name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


_lock = threading.Lock()
_queue: FireAndForget[TaskCall] | None = None


def get_queue() -> FireAndForget[TaskCall]:
    """Return the process-wide task queue, building it lazily."""
    global _queue  # noqa: PLW0603
    if _queue is not None:
        return _queue
    with _lock:
        if _queue is None:
            _queue = FireAndForget(
                _flush_batch,
                queue_size=10_000,
                batch_max=100,
                batch_interval_ms=20,
                metric_prefix="tasks",
                name="tasks",
            )
    return _queue


def submit(name: str, *args: Any, **kwargs: Any) -> bool:
    """Enqueue a task by name.

    Args:
        name: Registered task name (see :func:`tasks.register`).
        *args: Positional arguments forwarded to the handler.
        **kwargs: Keyword arguments forwarded to the handler.

    Returns:
        ``True`` when the task was queued, ``False`` on overflow.

    Raises:
        KeyError: ``name`` is not registered. Surface immediately so
            mis-typed task names are caught at submit time, not later.
    """
    # Validate at submit so a typo crashes the caller, not the worker.
    get_handler(name)
    return get_queue().submit(TaskCall(name=name, args=tuple(args), kwargs=dict(kwargs)))


async def _flush_batch(batch: Sequence[TaskCall]) -> None:
    """Run every task in the batch, swallowing + metering individual failures."""
    for call in batch:
        try:
            handler = get_handler(call.name)
        except KeyError:
            _logger.exception("Task handler %r vanished from registry.", call.name)
            get_metrics().incr("tasks.unknown", tags={"name": call.name})
            continue
        try:
            await handler(*call.args, **call.kwargs)
        except Exception:
            _logger.exception("Task %r failed.", call.name)
            get_metrics().incr("tasks.failed", tags={"name": call.name})


def reset_tasks() -> None:
    """Drop the cached queue (test hook + ``testing.reset_all_singletons``)."""
    global _queue  # noqa: PLW0603
    with _lock:
        _queue = None


__all__ = ["TaskCall", "get_queue", "reset_tasks", "submit"]
