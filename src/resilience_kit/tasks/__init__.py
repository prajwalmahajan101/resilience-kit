"""Lightweight in-process fire-and-forget task queue (ROADMAP M4).

Wraps :class:`~resilience_kit.dispatch.FireAndForget` with a name-keyed
registry so callers register coroutines once (``@register("send_email")``)
and submit work by name. No Celery dep, no broker — designed for the
common "make this fire-and-forget" pattern that does not need cross-
process delivery.

Public surface:

* :func:`register` — decorator that registers a coroutine under a name.
* :func:`submit` — enqueue a task call with positional / keyword args.
* :func:`get_queue` — obtain the queue (lazy build from settings).
* :func:`reset_tasks` — drop the cached queue (wired into ``testing.reset``).
"""

from __future__ import annotations

from resilience_kit.tasks.queue import get_queue, reset_tasks, submit
from resilience_kit.tasks.registry import register

__all__ = ["get_queue", "register", "reset_tasks", "submit"]
