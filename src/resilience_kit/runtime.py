"""Settings indirection — kit code never imports a global settings module.

Callers obtain settings through :func:`get_settings`, which resolves them
from a pluggable :class:`SettingsSource`. The default source loads from env
via pydantic-settings. Adapters (Django, FastAPI) swap in their own source
via :func:`set_settings_source`.

Tests reset the cached instance with :func:`reset_settings_cache` (part of
``testing.reset_all_singletons``).
"""

from __future__ import annotations

import os
import threading
import warnings
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from resilience_kit.exceptions import ValidationError
from resilience_kit.settings import ResilienceSettings

if TYPE_CHECKING:
    from collections.abc import Mapping, MutableMapping


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
    """Drop the cached settings + restore the default :class:`EnvSettingsSource`.

    Restoring the source matters for tests: an in-process test that swaps
    in a ``FixedSource`` via :func:`set_settings_source` must not leak that
    source into the next test. Wired into
    :func:`resilience_kit.testing.reset.reset_all_singletons`.
    """
    global _cached, _source  # noqa: PLW0603 — module-level reset is the API
    with _lock:
        _cached = None
        _source = EnvSettingsSource()


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


#: Translation table from pre-kit ("boilerplate") env-var names to the kit's
#: ``RESILIENCE_*`` schema. Mirrors ``docs/MIGRATION-from-boilerplate-embedded.md``
#: §10.5. Extend in a follow-up patch if more names surface during adoption.
DEFAULT_ALIASES: Mapping[str, str] = {
    "FIELD_ENCRYPTION_KEY": "RESILIENCE_CRYPTO__FIELD_ENCRYPTION_KEY",
    "REDIS_URL": "RESILIENCE_REDIS_URL",
    "OUTBOUND_ALLOWLIST": "RESILIENCE_SSRF__OUTBOUND_ALLOWLIST",
    "SSRF_ALLOWLIST": "RESILIENCE_SSRF__OUTBOUND_ALLOWLIST",
    "BLOCK_PRIVATE_IPS": "RESILIENCE_SSRF__BLOCK_PRIVATE_IPS",
    "RATE_LIMIT_ANON": "RESILIENCE_DEFAULTS__THROTTLE__ANON_RATE",
    "RATE_LIMIT_AUTH": "RESILIENCE_DEFAULTS__THROTTLE__AUTH_RATE",
    "RATE_LIMIT_BURST": "RESILIENCE_DEFAULTS__THROTTLE__BURST_RATE",
    "CIRCUIT_BREAKER_FAIL_MAX": "RESILIENCE_DEFAULTS__CIRCUIT_BREAKER__FAIL_MAX",
    "CIRCUIT_BREAKER_RESET_TIMEOUT": "RESILIENCE_DEFAULTS__CIRCUIT_BREAKER__RESET_TIMEOUT",
    "RECOVERY_PROBE_INTERVAL": "RESILIENCE_RECOVERY__PROBE_INTERVAL_SECONDS",
    "AUDIT_SINK": "RESILIENCE_AUDIT__SINK",
}


def legacy_env_alias(
    *,
    env: MutableMapping[str, str] | None = None,
    aliases: Mapping[str, str] = DEFAULT_ALIASES,
    warn: bool = True,
) -> dict[str, str]:
    """Translate pre-kit env-var names onto their ``RESILIENCE_*`` equivalents.

    Call once at the top of your settings module **before**
    :class:`ResilienceSettings` instantiates. Without this bridge the kit only
    reads ``RESILIENCE_*`` variables — deployments pinned on the older names
    (``RATE_LIMIT_AUTH``, ``CIRCUIT_BREAKER_FAIL_MAX``, ``FIELD_ENCRYPTION_KEY``
    …) silently lose their tuning. See MIGRATION §10.5.

    Behaviour:

    - If the legacy name is set and the kit name is **not** set, the kit name
      is populated with the legacy value and a :class:`DeprecationWarning`
      fires (suppressible via ``warn=False``).
    - If **both** are set, the kit name wins and a warning fires so operators
      catch ambiguous configs.
    - If only the kit name is set, the alias is a no-op.

    Args:
        env: Environment mapping to mutate. Defaults to :data:`os.environ`
            at call time (not at import time, so test injection works).
        aliases: Override the default table. Pass a narrower map if you only
            want to bridge a subset (and silence warnings for the rest).
        warn: When ``False``, suppress :class:`DeprecationWarning`. Useful in
            short-lived CI jobs where the legacy names are intentionally pinned.

    Returns:
        A dict of ``{legacy_name: new_name}`` for the aliases that were
        actually applied (copy or skip-due-to-collision). Caller can log it
        for an audit trail.
    """
    target = env if env is not None else os.environ
    applied: dict[str, str] = {}
    for legacy, new in aliases.items():
        legacy_val = target.get(legacy)
        if legacy_val is None:
            continue
        new_val = target.get(new)
        if new_val is None:
            target[new] = legacy_val
            applied[legacy] = new
            if warn:
                warnings.warn(
                    f"Env var {legacy!r} is deprecated; use {new!r}. "
                    f"resilience-kit copied the value for this process.",
                    DeprecationWarning,
                    stacklevel=2,
                )
        else:
            applied[legacy] = new
            if warn:
                warnings.warn(
                    f"Both {legacy!r} (legacy) and {new!r} are set; the kit will use {new!r}.",
                    DeprecationWarning,
                    stacklevel=2,
                )
    return applied
