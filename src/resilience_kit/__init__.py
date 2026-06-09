"""``prajwal-resilience-kit`` — framework-agnostic Python resilience kernel.

Public surface (M1):
    * Decorators — :func:`retry`, :func:`retry_on_failure`,
      :func:`circuit_breaker`, :func:`resilient`.
    * Registry — :class:`ResilienceRegistry`, :data:`registry`.
    * Exceptions — see :mod:`resilience_kit.exceptions`.

Backends and adapters land in later milestones (see ``docs/ROADMAP.md``).
"""

from __future__ import annotations

from resilience_kit._version import __version__
from resilience_kit.decorators import circuit_breaker, resilient
from resilience_kit.exceptions import (
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
)
from resilience_kit.registry import ResilienceRegistry, registry
from resilience_kit.retry import retry, retry_on_failure

__all__ = [
    "DecryptionError",
    "ExternalServiceError",
    "ExternalTimeoutError",
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
    "circuit_breaker",
    "registry",
    "resilient",
    "retry",
    "retry_on_failure",
]
