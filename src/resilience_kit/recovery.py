"""Background recovery monitor — re-probes degraded Redis backends.

Backends (cache / breaker / throttle) that flip to fail-open self-register
via :func:`register_for_recovery`. The monitor periodically calls
:meth:`try_recover` on each; on success the backend resumes primary
operation. Adapters launch ``monitor.start()`` from their lifespan /
AppConfig and ``await monitor.stop()`` on shutdown.

The probe interval is settings-driven (``RESILIENCE_RECOVERY__PROBE_INTERVAL_SECONDS``)
so tests inject 0.2 s while production runs at 10 s.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from resilience_kit.runtime import get_settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from resilience_kit.circuit_breaker.base import HealthSnapshot


_logger = logging.getLogger(__name__)


@runtime_checkable
class RecoverableBackend(Protocol):
    """A backend that can be polled by the recovery monitor."""

    async def try_recover(self) -> bool:
        """Probe the primary; on success, flip back from fallback.

        Returns:
            ``True`` if the backend successfully recovered on this call.
        """
        ...

    async def health_check(self) -> HealthSnapshot:
        """Return current health snapshot.

        Returns:
            Snapshot describing whether the backend is healthy.
        """
        ...


_lock = threading.Lock()
_registered: list[RecoverableBackend] = []
_warm_hooks: list[Callable[[], Awaitable[None]]] = []


def register_for_recovery(backend: RecoverableBackend) -> None:
    """Add ``backend`` to the recovery roster.

    Called by backend ``__init__`` methods. Idempotent — duplicate
    registrations are silently dropped.

    Args:
        backend: A backend exposing ``try_recover`` + ``health_check``.
    """
    with _lock:
        if backend not in _registered:
            _registered.append(backend)


def unregister_for_recovery(backend: RecoverableBackend) -> None:
    """Remove ``backend`` from the roster. No-op if absent.

    Args:
        backend: The backend to remove.
    """
    with _lock, contextlib.suppress(ValueError):
        _registered.remove(backend)


def registered_backends() -> list[RecoverableBackend]:
    """Return a snapshot of currently-registered backends.

    Returns:
        New list — safe to iterate without holding the lock.
    """
    with _lock:
        return list(_registered)


def register_warm_hook(hook: Callable[[], Awaitable[None]]) -> None:
    """Add a hook fired after any backend recovers.

    Use cases: prime caches, replay deferred writes, page oncall.

    Args:
        hook: Async callable taking no args.
    """
    with _lock:
        _warm_hooks.append(hook)


async def attempt_recover_all() -> int:
    """Probe every registered backend once.

    Runs warm hooks if any backend flipped back to healthy.

    Returns:
        Number of backends that successfully recovered on this tick.
    """
    recovered = 0
    for backend in registered_backends():
        try:
            if await backend.try_recover():
                recovered += 1
        except Exception:
            _logger.exception("recovery probe raised; ignoring")
    if recovered > 0:
        for hook in _warm_hooks:
            try:
                await hook()
            except Exception:
                _logger.exception("recovery warm hook raised; ignoring")
    return recovered


def reset_recovery_state() -> None:
    """Clear all registered backends + warm hooks. Test hook.

    Wired into :func:`resilience_kit.testing.reset.reset_all_singletons`.
    """
    with _lock:
        _registered.clear()
        _warm_hooks.clear()


class RecoveryMonitor:
    """Background asyncio task that periodically calls ``attempt_recover_all``.

    Lifecycle:

      * :meth:`start` — idempotent; spawns the background task.
      * :meth:`stop` — signals the task and awaits with a timeout.

    Probe interval comes from
    :attr:`~resilience_kit.settings.RecoverySettings.probe_interval_seconds`.
    """

    def __init__(self) -> None:
        """Initialise an idle monitor."""
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        """Spawn the background task. Idempotent.

        Raises:
            RuntimeError: No running event loop is available.
        """
        with self._lock:
            if self._task is not None and not self._task.done():
                return
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="resilience_kit.recovery_monitor")
        _logger.info("RecoveryMonitor started.")

    async def stop(self, timeout: float = 5.0) -> None:  # noqa: ASYNC109 — public API
        """Signal the task to stop and await it.

        Args:
            timeout: Seconds to wait before giving up and cancelling.
        """
        with self._lock:
            task = self._task
            if task is None:
                return
        self._stopping.set()
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        finally:
            with self._lock:
                self._task = None
        _logger.info("RecoveryMonitor stopped.")

    async def _run(self) -> None:
        """Main loop — wakes every ``probe_interval`` to check backends."""
        while not self._stopping.is_set():
            interval = float(get_settings().recovery.probe_interval_seconds)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)
            if self._stopping.is_set():
                break
            try:
                await attempt_recover_all()
            except Exception:
                _logger.exception("attempt_recover_all raised; continuing")


#: Process-wide singleton.
monitor = RecoveryMonitor()
