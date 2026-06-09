"""Shared fire-and-forget dispatch primitive (LLD §7).

The :class:`FireAndForget` worker is the building block shared by the
audit subsystem (:mod:`resilience_kit.audit.dispatch`) and the in-process
task queue (:mod:`resilience_kit.tasks.queue`). It owns a bounded queue,
a background worker task that drains it in batches, and a graceful drain
on shutdown.
"""

from __future__ import annotations

from resilience_kit.dispatch.fire_and_forget import FireAndForget, OverflowPolicy

__all__ = ["FireAndForget", "OverflowPolicy"]
