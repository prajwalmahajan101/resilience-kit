"""Build the audit dispatcher from settings (LLD §10).

Resolves the configured backend + sanitiser via the standard provider
chain (entry points → builtins → fail) and wraps them in a
:class:`FireAndForgetDispatcher`. The result is cached per-process so
decorators can call :func:`get_dispatcher` from any task without re-
building the wiring.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from resilience_kit._providers import resolve_provider
from resilience_kit.audit.backends.noop import NoopAuditBackend
from resilience_kit.audit.backends.stdlib_logging import StdlibLoggingAuditBackend
from resilience_kit.audit.dispatch import FireAndForgetDispatcher
from resilience_kit.audit.sanitizers import DefaultRedactor
from resilience_kit.runtime import get_settings

if TYPE_CHECKING:
    from collections.abc import Mapping

    from resilience_kit.audit.backends.base import AuditBackend
    from resilience_kit.audit.dispatch import AuditDispatcher
    from resilience_kit.audit.sanitizers import Sanitizer

_BACKEND_GROUP = "resilience_kit.audit_backends"
_SANITIZER_GROUP = "resilience_kit.audit_sanitizers"

_BUILTIN_BACKENDS: Mapping[str, Any] = {
    "noop": NoopAuditBackend,
    "stdlib_logging": StdlibLoggingAuditBackend,
}

_BUILTIN_SANITIZERS: Mapping[str, Any] = {
    "default": DefaultRedactor,
}

_lock = threading.Lock()
_dispatcher: AuditDispatcher | None = None


def get_dispatcher() -> AuditDispatcher:
    """Return the process-wide audit dispatcher, building it lazily.

    Resolution:

    1. Anything previously installed via :func:`set_dispatcher` wins.
    2. ``settings.audit.sink`` resolves the backend via the provider
       chain (explicit → string → entry point → builtin → fail).
    3. ``settings.audit.sanitizer`` resolves the sanitiser the same way.
    4. Both are wrapped in a :class:`FireAndForgetDispatcher` with
       queue/batch settings from ``settings.audit``.

    Returns:
        The active dispatcher.
    """
    global _dispatcher  # noqa: PLW0603
    if _dispatcher is not None:
        return _dispatcher
    with _lock:
        if _dispatcher is None:
            _dispatcher = _build_from_settings()
    return _dispatcher


def set_dispatcher(dispatcher: AuditDispatcher) -> None:
    """Install ``dispatcher`` as the process-wide dispatcher.

    Args:
        dispatcher: Replacement dispatcher — wins over the settings-
            driven default.
    """
    global _dispatcher  # noqa: PLW0603
    with _lock:
        _dispatcher = dispatcher


def reset_dispatcher() -> None:
    """Drop the cached dispatcher. Wired into ``testing.reset_all_singletons``."""
    global _dispatcher  # noqa: PLW0603
    with _lock:
        _dispatcher = None


def _build_from_settings() -> AuditDispatcher:
    settings = get_settings()
    backend: AuditBackend = resolve_provider(
        group=_BACKEND_GROUP,
        name=settings.audit.sink,
        builtins=_BUILTIN_BACKENDS,
    )
    sanitizer: Sanitizer = resolve_provider(
        group=_SANITIZER_GROUP,
        name=settings.audit.sanitizer,
        builtins=_BUILTIN_SANITIZERS,
        factory_kwargs={"fields": settings.audit.redact_fields},
    )
    return FireAndForgetDispatcher(
        backend,
        sanitizer=sanitizer,
        queue_size=settings.audit.queue_size,
        batch_max=settings.audit.batch_max,
        batch_interval_ms=settings.audit.batch_interval_ms,
    )


__all__ = ["get_dispatcher", "reset_dispatcher", "set_dispatcher"]
