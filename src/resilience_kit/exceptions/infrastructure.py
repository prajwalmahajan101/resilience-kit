"""Infrastructure-tier exceptions raised by the kit's primitives.

Layered so callers can catch broadly (``TransientError`` for "anything
retryable") or narrowly (``ExternalTimeoutError`` for "the call timed out
specifically"). The hierarchy is locked at v0.1 per PRD §5.4 / LLD §11.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.exceptions.base import ResilienceKitError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


class TransientError(ResilienceKitError):
    """A retryable failure that is expected to clear on its own.

    The kit's ``@retry`` decorator retries on this class by default; the
    circuit breaker counts it as a failure. Subclasses preserve that
    behaviour, so ``ExternalTimeoutError`` is also retryable.
    """

    error_code = "TRANSIENT_ERROR"


class ExternalTimeoutError(TransientError):
    """An upstream call did not complete in the allotted time."""

    error_code = "EXTERNAL_TIMEOUT"


class ExternalServiceError(ResilienceKitError):
    """An upstream service returned a non-success response.

    Not a ``TransientError`` — ``@retry`` does not retry by default, but the
    breaker counts it as a failure (this is the canonical "open the breaker"
    signal).
    """

    error_code = "EXTERNAL_SERVICE_ERROR"


class ServiceUnavailableError(ResilienceKitError):
    """The circuit breaker is OPEN — request short-circuited.

    Carries ``service_name`` so observability pipelines can attribute the
    short-circuit to a specific breaker. ``@retry`` filters this class out of
    ``retry_on`` so a retried call cannot defeat an OPEN breaker.
    """

    error_code = "SERVICE_UNAVAILABLE"

    def __init__(
        self,
        service_name: str,
        *,
        message: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialise with the breaker's service name.

        Args:
            service_name: Name of the breaker that short-circuited.
            message: Optional human-readable override.
            details: Optional extra structured payload.
        """
        merged: dict[str, Any] = {"service_name": service_name}
        if details:
            merged.update(details)
        super().__init__(message or f"Service '{service_name}' is unavailable.", details=merged)
        self.service_name = service_name


class RepositoryError(ResilienceKitError):
    """A storage-layer operation failed (DB, blob store, etc.)."""

    error_code = "REPOSITORY_ERROR"


class DecryptionError(ResilienceKitError):
    """A ciphertext could not be decrypted — likely key rotation or corruption."""

    error_code = "DECRYPTION_ERROR"


class MissingExtraError(ResilienceKitError):
    """A backend module was imported without its required pip extra.

    Raised at module import time (not at first use) so the failure mode is
    immediate and the install hint is obvious.
    """

    error_code = "MISSING_EXTRA"

    def __init__(self, extra: str, install_hint: str) -> None:
        """Initialise with the extra name and a paste-ready ``pip install`` hint.

        Args:
            extra: Name of the pip extra (e.g. ``"redis"``).
            install_hint: Full install string, e.g. ``"resilience-kit[redis]"``.
        """
        super().__init__(
            f"Optional dependency '{extra}' is not installed. "
            f"Install it with: pip install '{install_hint}'",
            details={"extra": extra, "install_hint": install_hint},
        )
        self.extra = extra
        self.install_hint = install_hint


class UnknownBackendError(ResilienceKitError):
    """A provider was asked for a backend name that does not resolve.

    Raised by ``_providers.resolve_provider`` (M2) — included at M1 so the
    public exception surface is locked from the first release.
    """

    error_code = "UNKNOWN_BACKEND"

    def __init__(self, group: str, name: str, available: Iterable[str]) -> None:
        """Initialise with the entry-point group, requested name, and known options.

        Args:
            group: Entry-point group queried (e.g. ``"resilience_kit.cache_backends"``).
            name: Backend name the caller asked for.
            available: Names of currently-resolvable backends.
        """
        avail = sorted(set(available))
        super().__init__(
            f"Backend {name!r} not found in group {group!r}. Available: {avail}",
            details={"group": group, "name": name, "available": avail},
        )
        self.group = group
        self.name = name
        self.available = tuple(avail)
