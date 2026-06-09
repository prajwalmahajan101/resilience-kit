"""Crypto-specific exceptions.

:class:`~resilience_kit.exceptions.DecryptionError` already lives in the
infrastructure tier and is reused here verbatim — re-exported for
ergonomics so callers ``from resilience_kit.crypto import DecryptionError``.
"""

from __future__ import annotations

from resilience_kit.exceptions import DecryptionError, ResilienceKitError


class FernetUnavailableError(ResilienceKitError):
    """``cryptography`` is not installed (Fernet cannot be loaded).

    Raised when :class:`resilience_kit.crypto.FernetCipher` is invoked
    in a process that did not install the ``crypto`` extra. Surfaced
    separately from :class:`~resilience_kit.exceptions.MissingExtraError`
    only because :meth:`FernetCipher.encrypt` / ``decrypt`` may be
    called from per-request code paths where the missing dependency
    should not look like an arbitrary internal error.
    """

    error_code = "FERNET_UNAVAILABLE"


class EncryptionConfigError(ResilienceKitError):
    """``field_encryption_key`` missing in a non-dev environment.

    The kit refuses to start the cipher without a key in
    ``settings.crypto.environment="prod"`` so silent fallback cannot
    corrupt encrypted columns on the next key rotation.
    """

    error_code = "ENCRYPTION_CONFIG_ERROR"


__all__ = ["DecryptionError", "EncryptionConfigError", "FernetUnavailableError"]
