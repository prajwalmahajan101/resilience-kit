"""Per-service config registry + breaker cache.

The registry merges :class:`~resilience_kit.settings.ResilienceSettings`
defaults with per-service overrides (caller passes types directly — no
dotted-string exception resolution, unlike the boilerplates). It also caches
constructed breakers so every call site for service ``"X"`` shares one
breaker.

Registration uses ``threading.Lock`` because services are typically
registered at process start from sync code (Django ``AppConfig.ready``,
FastAPI startup hook). Breaker hot-path mutations use ``asyncio.Lock``
inside each breaker implementation.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from resilience_kit.circuit_breaker.base import (
    DEFAULT_EXCLUDED_EXCEPTIONS,
    AsyncBreaker,
    BreakerConfig,
    HealthSnapshot,
)
from resilience_kit.circuit_breaker.provider import get_breaker as _build_breaker
from resilience_kit.exceptions import TransientError
from resilience_kit.runtime import get_settings

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Effective retry policy for one service after defaults + overrides merge."""

    max_attempts: int
    wait_min: float
    wait_max: float
    exponential_base: float
    jitter: str
    retry_on: tuple[type[BaseException], ...]


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    """Effective per-service config — retry + breaker."""

    name: str
    retry: RetryPolicy
    circuit_breaker: BreakerConfig


@dataclass(slots=True)
class _ServiceOverrides:
    """Caller-supplied overrides; deep-merged with defaults at read time."""

    retry: dict[str, Any] = field(default_factory=dict)
    circuit_breaker: dict[str, Any] = field(default_factory=dict)


class ResilienceRegistry:
    """Process-wide registry of services + their breakers.

    Thread-safe for registration (sync startup paths); breakers themselves
    are async-safe.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._lock = threading.Lock()
        self._overrides: dict[str, _ServiceOverrides] = {}
        self._breakers: dict[str, AsyncBreaker] = {}

    def register_service(self, name: str, overrides: Mapping[str, Any]) -> None:
        """Record per-service overrides that win over settings defaults.

        Args:
            name: Service identifier (used by ``@resilient(name)``).
            overrides: Mapping with optional ``retry`` and ``circuit_breaker``
                sub-dicts.
        """
        retry_over = dict(overrides.get("retry", {}))
        cb_over = dict(overrides.get("circuit_breaker", {}))
        with self._lock:
            self._overrides[name] = _ServiceOverrides(retry=retry_over, circuit_breaker=cb_over)
            # Drop any cached breaker so the next get_breaker rebuilds with the
            # new config.
            self._breakers.pop(name, None)

    def get_config(self, name: str) -> ServiceConfig:
        """Return the effective config for service ``name``.

        Defaults from :class:`ResilienceSettings`; overrides from
        :meth:`register_service` win on a field-by-field basis.

        Args:
            name: Service identifier.

        Returns:
            Effective :class:`ServiceConfig`.
        """
        settings = get_settings()
        defaults_retry = settings.defaults.retry
        defaults_cb = settings.defaults.circuit_breaker
        over = self._overrides.get(name)
        retry_over = over.retry if over else {}
        cb_over = over.circuit_breaker if over else {}

        retry = RetryPolicy(
            max_attempts=int(retry_over.get("max_attempts", defaults_retry.max_attempts)),
            wait_min=float(retry_over.get("wait_min", defaults_retry.wait_min)),
            wait_max=float(retry_over.get("wait_max", defaults_retry.wait_max)),
            exponential_base=float(
                retry_over.get("exponential_base", defaults_retry.exponential_base),
            ),
            jitter=str(retry_over.get("jitter", defaults_retry.jitter)),
            retry_on=_normalise_retry_on(retry_over.get("retry_on")),
        )
        cb = BreakerConfig(
            fail_max=int(cb_over.get("fail_max", defaults_cb.fail_max)),
            reset_timeout=float(cb_over.get("reset_timeout", defaults_cb.reset_timeout)),
            success_threshold=int(
                cb_over.get("success_threshold", defaults_cb.success_threshold),
            ),
            excluded_exceptions=tuple(
                cb_over.get("excluded_exceptions", DEFAULT_EXCLUDED_EXCEPTIONS),
            ),
        )
        return ServiceConfig(name=name, retry=retry, circuit_breaker=cb)

    def get_breaker(self, name: str) -> AsyncBreaker:
        """Return the cached breaker for ``name``, building it on first call.

        Args:
            name: Service identifier.

        Returns:
            The per-service breaker. All call sites for ``name`` share it.
        """
        cached = self._breakers.get(name)
        if cached is not None:
            return cached
        with self._lock:
            cached = self._breakers.get(name)
            if cached is None:
                cached = _build_breaker(
                    name=name,
                    config=self.get_config(name).circuit_breaker,
                )
                self._breakers[name] = cached
        return cached

    async def health_snapshot(self) -> dict[str, HealthSnapshot]:
        """Probe every cached breaker.

        Returns:
            ``{service_name: HealthSnapshot}`` for all known breakers.
        """
        snap: dict[str, HealthSnapshot] = {}
        for name, breaker in list(self._breakers.items()):
            snap[name] = await breaker.health_check()
        return snap

    def reset(self) -> None:
        """Drop all registrations + cached breakers. Test hook."""
        with self._lock:
            self._overrides.clear()
            self._breakers.clear()


def _normalise_retry_on(
    raw: object,
) -> tuple[type[BaseException], ...]:
    """Validate ``retry_on`` is a tuple/list of exception classes.

    Args:
        raw: Caller-supplied value (``None`` → default = ``(TransientError,)``).

    Returns:
        Validated tuple.

    Raises:
        TypeError: ``raw`` contains a non-exception class.
    """
    if raw is None:
        return (TransientError,)
    if not isinstance(raw, tuple | list):
        raise TypeError(
            f"retry_on must be a tuple/list of exception classes, got {type(raw).__name__}",
        )
    out: list[type[BaseException]] = []
    for item in raw:
        if not isinstance(item, type) or not issubclass(item, BaseException):
            raise TypeError(f"retry_on entries must be exception classes, got {item!r}")
        out.append(item)
    return tuple(out)


#: Process-wide registry. Callers usually use this singleton; multiple
#: registries are supported for tests but rarely needed in app code.
registry = ResilienceRegistry()


def reset_registry() -> None:
    """Clear the process-wide registry. Wired into ``testing.reset_all_singletons``."""
    registry.reset()
