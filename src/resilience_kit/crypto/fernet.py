"""Field-level Fernet encryption (AES-128-CBC + HMAC-SHA256).

Single source of truth for plaintext ↔ ciphertext round-trips used by
the SQLAlchemy ``EncryptedString`` (M5) and the Django
``EncryptedCharField`` (M6).

Key derivation::

    digest = sha256(field_encryption_key)
    fernet_key = base64.urlsafe_b64encode(digest)
    Fernet(fernet_key)

A dedicated ``field_encryption_key`` (vs. reusing an application
``secret_key``) means that routine rotation of any other secret cannot
accidentally corrupt encrypted columns.

Environment guard:

* ``settings.crypto.environment="prod"`` (default) + no key
  → :class:`EncryptionConfigError` at first ``encrypt`` / ``decrypt``.
* ``"dev"`` / ``"test"`` + no key
  → one-time warning, falls back to a static well-known dev key so
  local boots work. The dev key is **insecure on purpose** so it can
  never accidentally end up in production data.

This module imports :mod:`cryptography`; importing it without the
``crypto`` extra raises
:class:`~resilience_kit.exceptions.MissingExtraError` at import time.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import logging

from resilience_kit.crypto.exceptions import (
    DecryptionError,
    EncryptionConfigError,
)
from resilience_kit.exceptions import MissingExtraError
from resilience_kit.runtime import get_settings

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("crypto", "resilience-kit[crypto]") from exc

logger = logging.getLogger(__name__)

#: Sentinel dev-only key. Reused across the kit's dev/test fallback so
#: ciphertext written under one dev run is decryptable in the next.
#: NEVER use this in prod: the value is hard-coded and public.
_DEV_FALLBACK_KEY = "resilience-kit::dev-only-insecure::do-not-use-in-prod"


@functools.lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Return the process-wide :class:`Fernet` instance, built lazily.

    The instance is cached so every encrypt/decrypt uses the same key
    without re-deriving the SHA-256 digest. Tests reset the cache via
    :func:`reset_fernet_cache`.

    Returns:
        Configured :class:`Fernet` ready for ``encrypt`` / ``decrypt``.

    Raises:
        FernetUnavailableError: ``cryptography`` is missing — should be
            impossible since the import guard at module load would have
            raised :class:`MissingExtraError` first; included for
            type-safety symmetry with the public API.
        EncryptionConfigError: ``field_encryption_key`` is unset in a
            non-dev environment.
    """
    settings = get_settings()
    secret = settings.crypto.field_encryption_key
    if secret is not None:
        key_source = secret.get_secret_value()
    else:
        if settings.crypto.environment == "prod":
            raise EncryptionConfigError(
                "field_encryption_key must be set when "
                "settings.crypto.environment='prod'. Silent fallback is "
                "disabled to prevent data corruption on key rotation.",
                details={"environment": settings.crypto.environment},
            )
        logger.warning(
            "FernetCipher: field_encryption_key not set; using insecure dev "
            "fallback (environment=%s).",
            settings.crypto.environment,
        )
        key_source = _DEV_FALLBACK_KEY

    digest = hashlib.sha256(key_source.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def reset_fernet_cache() -> None:
    """Clear the :func:`_fernet` cache — used by the testing reset helper."""
    _fernet.cache_clear()


class FernetCipher:
    """Encrypt / decrypt strings with the application's Fernet key."""

    @staticmethod
    def encrypt(plaintext: str) -> str:
        """Encrypt ``plaintext`` with the configured key.

        Empty strings pass through unchanged so an ``EncryptedString``
        round-trip survives without forcing a sentinel value in the DB.

        Args:
            plaintext: UTF-8 source text.

        Returns:
            Fernet ciphertext (URL-safe base64), or the original empty
            string when input is empty.

        Raises:
            FernetUnavailableError: ``cryptography`` is not installed.
            EncryptionConfigError: ``field_encryption_key`` is unset in
                a non-dev environment.
        """
        if not plaintext:
            return plaintext
        return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")

    @staticmethod
    def decrypt(ciphertext: str) -> str:
        """Decrypt ``ciphertext`` with the configured key.

        Empty strings pass through unchanged, mirroring :meth:`encrypt`.
        :class:`cryptography.fernet.InvalidToken` is converted into a
        domain-specific :class:`DecryptionError` so callers can map it
        onto a 500 response without exposing crypto internals.

        Args:
            ciphertext: Fernet token (URL-safe base64).

        Returns:
            Decrypted plaintext, or the original empty string.

        Raises:
            FernetUnavailableError: ``cryptography`` is not installed.
            EncryptionConfigError: ``field_encryption_key`` is unset in
                a non-dev environment.
            DecryptionError: The token is invalid (key rotation or
                ciphertext corruption).
        """
        if not ciphertext:
            return ciphertext
        try:
            return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            logger.error(
                "FernetCipher decrypt failed — possible key rotation or corruption.",
            )
            raise DecryptionError(
                "Failed to decrypt field value. Check field_encryption_key.",
            ) from exc


__all__ = ["FernetCipher", "reset_fernet_cache"]
