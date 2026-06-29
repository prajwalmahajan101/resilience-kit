"""Django :class:`AppConfig` for the resilience-kit adapter.

``ResilienceConfig.ready()`` runs once per Django process — twice if the
autoreloader is active, hence the idempotency guard. It performs three
jobs:

1. Reads ``settings.RESILIENCE`` (a dict the project supplies) and calls
   :meth:`ResilienceRegistry.register_service` for each declared
   service so ``@resilient(name)`` sees the right retry / breaker
   config.

2. Spawns a daemon thread that owns a private :mod:`asyncio` loop and
   drives :data:`recovery.monitor`. Django is sync-first so there is no
   ambient loop the monitor can attach to; the daemon thread bridges
   that gap. The thread is daemon=True so it dies with the worker —
   acceptable because the monitor is purely re-probing, never holding
   un-flushed state. ADR 0011 documents the bridge in detail.

3. Registers an :func:`atexit` hook to call :meth:`monitor.stop` and
   drain the audit dispatcher on graceful exit. Daemon-thread death on
   SIGKILL still loses in-flight audit events; the
   :class:`FireAndForgetDispatcher` design accepts that.

Reading ``settings.RESILIENCE`` lazily inside ``ready()`` (not at
module import) keeps the adapter importable in projects that do not
configure it yet, which makes the install a one-liner in
``INSTALLED_APPS``.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from typing import TYPE_CHECKING, Any

from resilience_kit.exceptions import MissingExtraError
from resilience_kit.recovery import monitor

try:
    from django.apps import AppConfig
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("django", "resilience-kit[django]") from exc

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger = logging.getLogger("resilience_kit.adapters.django")

_lock = threading.Lock()
_thread: threading.Thread | None = None
_loop: asyncio.AbstractEventLoop | None = None
_shutdown_event: threading.Event | None = None


class ResilienceConfig(AppConfig):  # type: ignore[misc]  # django.apps untyped — see mypy.ini
    """Adapter ``AppConfig`` — registers services and starts the monitor."""

    name = "resilience_kit.adapters.django"
    label = "resilience_kit"
    verbose_name = "Resilience kit"

    def ready(self) -> None:
        """Register services and ensure the recovery thread is running."""
        from django.conf import settings as django_settings  # noqa: PLC0415

        from resilience_kit.registry import registry  # noqa: PLC0415

        services: Mapping[str, Mapping[str, Any]] = getattr(
            django_settings,
            "RESILIENCE",
            {},
        ).get("services", {})
        for name, overrides in services.items():
            registry.register_service(name, overrides)

        _ensure_monitor_thread()


def _ensure_monitor_thread() -> None:
    """Spawn the daemon thread that owns the monitor's asyncio loop.

    Idempotent — guards against AppConfig.ready() being called twice by
    the autoreloader.
    """
    global _thread, _shutdown_event  # noqa: PLW0603
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _shutdown_event = threading.Event()
        ready = threading.Event()
        _thread = threading.Thread(
            target=_run_loop,
            args=(ready,),
            name="resilience_kit.recovery_monitor",
            daemon=True,
        )
        _thread.start()
        # Block briefly so callers know the loop is up before they
        # schedule work on it.
        ready.wait(timeout=2.0)
        atexit.register(_shutdown_monitor_thread)
        _logger.info("Resilience monitor thread started.")


def get_kit_loop() -> asyncio.AbstractEventLoop:
    """Return the adapter's persistent daemon-thread loop, starting it if needed.

    The loop is owned by the recovery-monitor thread and lives for the
    whole process. Coroutines bridged onto it (e.g. DRF throttle checks,
    #C6) therefore share **one** long-lived loop, so async primitives
    (locks, events, the redis client) bound to it never rebind across
    calls — the cross-loop failure mode that per-call ``asyncio.run``
    suffers under (see ADR-0011). Idempotent: safe to call before
    ``AppConfig.ready()`` has run.

    Returns:
        The running event loop owned by the monitor thread.

    Raises:
        RuntimeError: The monitor thread failed to bring a loop up.
    """
    _ensure_monitor_thread()
    if _loop is None:  # pragma: no cover - only if the thread failed to start
        raise RuntimeError(
            "resilience-kit recovery-monitor loop is not available; "
            "the daemon thread failed to start.",
        )
    return _loop


def _run_loop(ready: threading.Event) -> None:
    """Body of the daemon thread — owns a private asyncio loop."""
    global _loop  # noqa: PLW0603
    loop = asyncio.new_event_loop()
    _loop = loop
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_drive_monitor(ready))
    finally:
        loop.close()


async def _drive_monitor(ready: threading.Event) -> None:
    """Start the monitor, park until shutdown, then drain audit + stop."""
    from resilience_kit.audit.factory import get_dispatcher  # noqa: PLC0415

    monitor.start()
    ready.set()
    assert _shutdown_event is not None  # set by _ensure_monitor_thread.
    # Poll the threading.Event without blocking the loop. The 0.5 s
    # cadence is fast enough for tests and cheap enough for prod.
    # ASYNC110 suggests asyncio.Event but the signal originates from a
    # different thread (the atexit hook), so a threading.Event polled
    # from this loop is the correct primitive.
    while not _shutdown_event.is_set():  # noqa: ASYNC110
        await asyncio.sleep(0.5)
    # Drain audit + stop monitor on this loop BEFORE _run_loop closes
    # it. Doing this from the atexit hook would post coroutines to a
    # closed loop.
    try:
        await get_dispatcher().aclose(drain_timeout=5.0)
    except Exception:
        _logger.exception("Audit dispatcher drain raised during shutdown")
    await monitor.stop()


def _shutdown_monitor_thread() -> None:
    """Atexit hook: signal the loop thread to drain + stop, then join."""
    global _thread, _loop, _shutdown_event  # noqa: PLW0603
    if _shutdown_event is None or _thread is None:
        return
    _shutdown_event.set()
    _thread.join(timeout=8.0)
    _thread = None
    _loop = None
    _shutdown_event = None


__all__ = ["ResilienceConfig", "get_kit_loop"]
