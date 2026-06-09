"""Public exception hierarchy for ``resilience_kit``.

See LLD §11 for the exception ↔ HTTP mapping that adapters enforce.
"""

from __future__ import annotations

from resilience_kit.exceptions.base import ResilienceKitError
from resilience_kit.exceptions.infrastructure import (
    DecryptionError,
    ExternalServiceError,
    ExternalTimeoutError,
    MissingExtraError,
    RepositoryError,
    ServiceUnavailableError,
    TransientError,
    UnknownBackendError,
)
from resilience_kit.exceptions.validation import RateLimitError, ValidationError

__all__ = [
    "DecryptionError",
    "ExternalServiceError",
    "ExternalTimeoutError",
    "MissingExtraError",
    "RateLimitError",
    "RepositoryError",
    "ResilienceKitError",
    "ServiceUnavailableError",
    "TransientError",
    "UnknownBackendError",
    "ValidationError",
]
