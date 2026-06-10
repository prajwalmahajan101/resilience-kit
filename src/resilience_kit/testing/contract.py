"""Pytest helper to verify an adopter's exception handler matches their envelope.

Adopters that layer their own exception handlers on top of (or instead of) the
kit's :func:`resilience_kit.adapters.fastapi.install_exception_handlers` need a
way to assert, in their own test suite, that the *resulting* envelope shape
still validates against their schema for **every** kit exception class — not
just the one they happened to write a test for.

:func:`verify_envelope_contract` instantiates every kit exception with minimal
realistic kwargs, runs each through the adopter's handler, and feeds the result
to the adopter's schema validator. Failures from every exception class are
collected into a single :class:`AssertionError` so CI surfaces the full picture
in one shot instead of one-class-at-a-time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.exceptions import (
    DecryptionError,
    ExternalServiceError,
    ExternalTimeoutError,
    RateLimitError,
    RepositoryError,
    ResilienceKitError,
    ServiceUnavailableError,
    TransientError,
    UnknownBackendError,
    ValidationError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence


def _build_validation_error() -> ResilienceKitError:
    return ValidationError("invalid input", details={"field": "x"})


def _build_rate_limit_error() -> ResilienceKitError:
    return RateLimitError(limit=60, remaining=0, reset_at=0, retry_after=1.0, scope="ip")


def _build_service_unavailable() -> ResilienceKitError:
    return ServiceUnavailableError("payments")


def _build_external_timeout() -> ResilienceKitError:
    return ExternalTimeoutError("upstream timed out")


def _build_external_service() -> ResilienceKitError:
    return ExternalServiceError("upstream 502")


def _build_decryption_error() -> ResilienceKitError:
    return DecryptionError("ciphertext invalid")


def _build_repository_error() -> ResilienceKitError:
    return RepositoryError("db unreachable")


def _build_transient_error() -> ResilienceKitError:
    return TransientError("flaky path")


def _build_unknown_backend() -> ResilienceKitError:
    return UnknownBackendError("resilience_kit.cache_backends", "foo", ["memory", "redis"])


#: Builders for every HTTP-reachable kit exception. ``MissingExtraError`` is
#: deliberately excluded — it's a startup-time error that never reaches the
#: response envelope path. Keep in sync with LLD §11 if new classes ship.
_DEFAULT_BUILDERS: Mapping[type[ResilienceKitError], Callable[[], ResilienceKitError]] = {
    ValidationError: _build_validation_error,
    RateLimitError: _build_rate_limit_error,
    ServiceUnavailableError: _build_service_unavailable,
    ExternalTimeoutError: _build_external_timeout,
    ExternalServiceError: _build_external_service,
    DecryptionError: _build_decryption_error,
    RepositoryError: _build_repository_error,
    TransientError: _build_transient_error,
    UnknownBackendError: _build_unknown_backend,
}

#: Default exception classes :func:`verify_envelope_contract` will exercise.
DEFAULT_KIT_EXCEPTIONS: tuple[type[ResilienceKitError], ...] = tuple(_DEFAULT_BUILDERS.keys())


def _instantiate(cls: type[ResilienceKitError]) -> ResilienceKitError:
    builder = _DEFAULT_BUILDERS.get(cls)
    if builder is not None:
        return builder()
    # Unknown subclass — best-effort: try the base-class signature.
    return cls("dogfood")


def verify_envelope_contract(
    *,
    handler: Callable[[ResilienceKitError], Any],
    envelope_schema: Callable[[Any], Any],
    exceptions: Sequence[type[ResilienceKitError]] = DEFAULT_KIT_EXCEPTIONS,
) -> None:
    """Assert ``handler`` produces an envelope ``envelope_schema`` accepts for every kit exception.

    Args:
        handler: The adopter's exception handler. Called once per exception
            class with a freshly built instance. Whatever it returns is fed
            verbatim to ``envelope_schema`` — typically a dict (raw body),
            but a Starlette / DRF response works too if the adopter's
            ``envelope_schema`` knows how to read its body.
        envelope_schema: A one-arg callable that validates whatever
            ``handler`` returned. Use ``MyEnvelope.model_validate`` for
            a pydantic envelope, or any function that raises on mismatch.
        exceptions: Override the default class set. Pass a narrower tuple
            if the adopter only emits kit envelopes for a subset.

    Raises:
        AssertionError: If any exception's handler output fails the schema.
            The message lists **every** failing class so CI shows the full
            picture in a single run.
    """
    failures: list[str] = []
    for cls in exceptions:
        exc = _instantiate(cls)
        try:
            result = handler(exc)
            envelope_schema(result)
        except Exception as e:
            failures.append(f"{cls.__name__}: {type(e).__name__}: {e}")
    if failures:
        raise AssertionError(
            "Envelope contract failed for the following kit exceptions:\n  - "
            + "\n  - ".join(failures)
        )
