"""Settings indirection — kit code never imports a global settings module.

Callers obtain settings through :func:`get_settings`, which resolves them
from a pluggable :class:`SettingsSource`. The default source loads from env
via pydantic-settings. Adapters (Django, FastAPI) swap in their own source
via :func:`set_settings_source`.

Tests reset the cached instance with :func:`reset_settings_cache` (part of
``testing.reset_all_singletons``).
"""

from __future__ import annotations

import threading
from typing import Any, Protocol, runtime_checkable

from resilience_kit.exceptions import ValidationError
from resilience_kit.settings import ResilienceSettings


@runtime_checkable
class SettingsSource(Protocol):
    """Provide a fully-resolved :class:`ResilienceSettings` instance."""

    def load(self) -> ResilienceSettings:
        """Return a fully-resolved settings instance.

        Returns:
            Fully-resolved :class:`ResilienceSettings`.
        """
        ...


class EnvSettingsSource:
    """Default source — load from environment via pydantic-settings."""

    def load(self) -> ResilienceSettings:
        """Construct :class:`ResilienceSettings` from process env.

        Returns:
            Fully-resolved settings.
        """
        return ResilienceSettings()


_lock = threading.Lock()
_source: SettingsSource = EnvSettingsSource()
_cached: ResilienceSettings | None = None


def set_settings_source(source: SettingsSource) -> None:
    """Install ``source`` as the global settings source and clear the cache.

    Args:
        source: New source; must satisfy the :class:`SettingsSource` protocol.
    """
    global _source, _cached  # noqa: PLW0603 — module-level swap is the API
    with _lock:
        _source = source
        _cached = None


def get_settings() -> ResilienceSettings:
    """Return the process-wide :class:`ResilienceSettings` singleton.

    Lazy: built on first call from the installed source and cached. Tests
    clear the cache via :func:`reset_settings_cache`.

    Returns:
        The cached settings instance.
    """
    global _cached  # noqa: PLW0603 — module-level cache is the API
    if _cached is not None:
        return _cached
    with _lock:
        if _cached is None:
            _cached = _source.load()
    return _cached


def reset_settings_cache() -> None:
    """Drop the cached settings so the next ``get_settings()`` rebuilds it.

    Wired into :func:`resilience_kit.testing.reset.reset_all_singletons`.
    """
    global _cached  # noqa: PLW0603 — module-level cache reset is the API
    with _lock:
        _cached = None


def require(value: Any, *, name: str) -> Any:
    """Raise :class:`ValidationError` when ``value`` is falsy.

    Args:
        value: The value to validate.
        name: Setting key — used as the ``details`` field on the error.

    Returns:
        ``value`` unchanged when truthy.

    Raises:
        ValidationError: ``value`` is ``None``, empty, or ``False``.
    """
    if not value:
        raise ValidationError(
            f"Required setting {name!r} is not configured.",
            details={"setting": name},
        )
    return value
