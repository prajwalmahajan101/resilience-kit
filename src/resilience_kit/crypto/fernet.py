"""Field-level Fernet encryption (AES-128-CBC + HMAC-SHA256).

Single source of truth for plaintext ↔ ciphertext round-trips used by
the SQLAlchemy ``EncryptedString`` (M5) and the Django
``EncryptedCharField`` (M6).

Key resolution (#B6):

* If a configured key is already a valid Fernet key (32 url-safe base64
  bytes, e.g. from ``Fernet.generate_key()``) it is used **directly**.
  This is the recommended path — give the kit a real key.
* Otherwise the value is treated as a passphrase and the key is derived via
  ``base64.urlsafe_b64encode(sha256(passphrase))``. This path is **deprecated**
  (unsalted, no work factor — weak for low-entropy passphrases) and emits a
  one-time warning. It is retained only so data encrypted by earlier versions
  still decrypts; supply a real Fernet key for new deployments.

Key rotation (#C1, ADR-0014):

* ``settings.crypto.field_encryption_keys`` is an *ordered* list — primary
  first, then older keys kept for decrypt-only. The cipher is a
  :class:`~cryptography.fernet.MultiFernet`: it encrypts with the primary and
  decrypts by trying each key in turn, so an old token written under a retired
  key still decrypts. No explicit per-token key-version prefix is needed —
  Fernet tokens already carry a version byte + timestamp and ``MultiFernet``
  trials each key. :meth:`FernetCipher.rotate` re-encrypts an existing token
  under the current primary without exposing plaintext.

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
    from cryptography.fernet import Fernet, InvalidToken, MultiFernet
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("crypto", "resilience-kit[crypto]") from exc

logger = logging.getLogger(__name__)

#: Sentinel dev-only key. Reused across the kit's dev/test fallback so
#: ciphertext written under one dev run is decryptable in the next.
#: NEVER use this in prod: the value is hard-coded and public.
_DEV_FALLBACK_KEY = "resilience-kit::dev-only-insecure::do-not-use-in-prod"


@functools.lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    """Return the process-wide :class:`MultiFernet` instance, built lazily.

    The instance is cached so every encrypt/decrypt reuses the resolved
    keys without re-deriving them. Encryption uses the primary (first)
    key; decryption tries each configured key in order. Tests reset the
    cache via :func:`reset_fernet_cache`.

    Returns:
        Configured :class:`MultiFernet` ready for ``encrypt`` /
        ``decrypt`` / ``rotate``.

    Raises:
        EncryptionConfigError: No key material is configured in a non-dev
            environment.
    """
    settings = get_settings()
    key_sources = settings.crypto.ordered_keys()
    if key_sources:
        return MultiFernet(
            [Fernet(_resolve_fernet_key(k, warn_on_legacy=True)) for k in key_sources],
        )

    if settings.crypto.environment == "prod":
        raise EncryptionConfigError(
            "field_encryption_key must be set (or the field_encryption_keys "
            "list) when settings.crypto.environment='prod'. Silent fallback is "
            "disabled to prevent data corruption on key rotation.",
            details={"environment": settings.crypto.environment},
        )
    logger.warning(
        "FernetCipher: no field-encryption key set; using insecure dev fallback (environment=%s).",
        settings.crypto.environment,
    )
    # The dev fallback is intentionally a passphrase and already warned about
    # above; don't double-warn it as a deprecated derivation.
    return MultiFernet([Fernet(_resolve_fernet_key(_DEV_FALLBACK_KEY, warn_on_legacy=False))])


def _resolve_fernet_key(key_source: str, *, warn_on_legacy: bool) -> bytes:
    """Return the Fernet key bytes for ``key_source``.

    Prefers a directly-supplied Fernet key; falls back to the deprecated
    SHA-256 derivation for passphrases so legacy ciphertext stays readable.

    Args:
        key_source: The configured key or passphrase.
        warn_on_legacy: Emit the deprecation warning when falling back to
            SHA-256 derivation (suppressed for the dev fallback).

    Returns:
        Bytes accepted by :class:`~cryptography.fernet.Fernet`.
    """
    raw = key_source.encode("utf-8")
    try:
        # Fernet's constructor validates "32 url-safe base64-encoded bytes";
        # if it accepts the value, it's a real key — use it directly.
        Fernet(raw)
    except (ValueError, TypeError):
        pass
    else:
        return raw

    if warn_on_legacy:
        logger.warning(
            "FernetCipher: field_encryption_key is a passphrase, not a Fernet "
            "key; deriving via unsalted SHA-256. This is weak for low-entropy "
            "inputs and is deprecated — supply a real key from "
            "Fernet.generate_key(). Existing data stays decryptable.",
        )
    digest = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(digest)


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

    @staticmethod
    def rotate(token: str) -> str:
        """Re-encrypt ``token`` under the current primary key.

        Decrypts with whichever configured key wrote the token and
        re-encrypts under the primary, without exposing plaintext. Use
        during key rotation to migrate stored ciphertext off a retired
        key onto the new primary (see ``docs/key-rotation.md``).

        Empty strings pass through unchanged, mirroring :meth:`encrypt`.

        Args:
            token: An existing Fernet token written under any configured key.

        Returns:
            A new token encrypted under the primary key, or the original
            empty string.

        Raises:
            EncryptionConfigError: No key material is configured in a
                non-dev environment.
            DecryptionError: The token is not decryptable under any
                configured key (retired beyond the key list, or corrupt).
        """
        if not token:
            return token
        try:
            return _fernet().rotate(token.encode("ascii")).decode("ascii")
        except InvalidToken as exc:
            logger.error(
                "FernetCipher rotate failed — token not decryptable under any configured key.",
            )
            raise DecryptionError(
                "Failed to rotate field value. The token's key is not in field_encryption_keys.",
            ) from exc


__all__ = ["FernetCipher", "reset_fernet_cache"]
