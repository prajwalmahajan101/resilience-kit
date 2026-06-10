"""``resilience-kit`` — framework-agnostic Python resilience kernel.

Public surface:

* Decorators — :func:`retry`, :func:`retry_on_failure`,
  :func:`circuit_breaker`, :func:`resilient`.
* Registry — :class:`ResilienceRegistry`, :data:`registry`.
* Exceptions — see :mod:`resilience_kit.exceptions`.
* SSRF guard — :func:`resolve_and_validate`, :func:`assert_public_url`,
  :func:`assert_allowed_url` (M3).
* HTTP client — :class:`AsyncAPIClient`, :func:`pinned` (M3, requires
  the ``http`` extra; imported lazily so users without the extra still
  ``import resilience_kit``).
* Field crypto — :class:`FernetCipher` (M3, requires the ``crypto``
  extra; imported lazily).

Backends and adapters land in later milestones (see ``docs/ROADMAP.md``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit._version import __version__
from resilience_kit.audit import AuditEvent, log_inbound, log_outbound
from resilience_kit.decorators import circuit_breaker, resilient
from resilience_kit.exceptions import (
    HTTP_STATUS_MAP,
    DecryptionError,
    ExternalServiceError,
    ExternalTimeoutError,
    MissingExtraError,
    RateLimitError,
    RepositoryError,
    ResilienceKitError,
    ServiceUnavailableError,
    TransientError,
    UnknownBackendError,
    ValidationError,
    http_status_for,
)
from resilience_kit.health import HealthAggregate, HealthStatus, health_snapshot
from resilience_kit.registry import ResilienceRegistry, registry
from resilience_kit.retry import retry, retry_on_failure
from resilience_kit.ssrf import (
    assert_allowed_url,
    assert_public_url,
    resolve_and_validate,
)

if TYPE_CHECKING:
    from resilience_kit.crypto import FernetCipher
    from resilience_kit.http_client import AsyncAPIClient, pinned

# Lazy re-exports for optional-extra-gated names.
# Importing the kit without ``[http]`` / ``[crypto]`` must not fail.
_LAZY: dict[str, tuple[str, str]] = {
    "AsyncAPIClient": ("resilience_kit.http_client", "AsyncAPIClient"),
    "pinned": ("resilience_kit.http_client", "pinned"),
    "FernetCipher": ("resilience_kit.crypto", "FernetCipher"),
}


def __getattr__(name: str) -> Any:
    """Resolve optional-extra-gated names lazily on first access.

    Importing :mod:`resilience_kit` itself must not require the
    ``[http]`` or ``[crypto]`` extras. The names below are resolved at
    attribute-access time; missing the extra surfaces as
    :class:`MissingExtraError` (raised by the submodule's import guard).

    Args:
        name: Attribute name being accessed.

    Returns:
        The resolved attribute.

    Raises:
        AttributeError: ``name`` is not exposed by this package.
    """
    if name in _LAZY:
        module_path, attr = _LAZY[name]
        import importlib  # noqa: PLC0415

        return getattr(importlib.import_module(module_path), attr)
    msg = f"module 'resilience_kit' has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "HTTP_STATUS_MAP",
    "AsyncAPIClient",
    "AuditEvent",
    "DecryptionError",
    "ExternalServiceError",
    "ExternalTimeoutError",
    "FernetCipher",
    "HealthAggregate",
    "HealthStatus",
    "MissingExtraError",
    "RateLimitError",
    "RepositoryError",
    "ResilienceKitError",
    "ResilienceRegistry",
    "ServiceUnavailableError",
    "TransientError",
    "UnknownBackendError",
    "ValidationError",
    "__version__",
    "assert_allowed_url",
    "assert_public_url",
    "circuit_breaker",
    "health_snapshot",
    "http_status_for",
    "log_inbound",
    "log_outbound",
    "pinned",
    "registry",
    "resilient",
    "resolve_and_validate",
    "retry",
    "retry_on_failure",
]
