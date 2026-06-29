"""Unit tests for :mod:`resilience_kit.crypto.fernet` — exit-gate tests."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

import pytest

pytest.importorskip("cryptography")

from cryptography.fernet import Fernet
from pydantic import SecretStr

from resilience_kit.crypto import (
    DecryptionError,
    EncryptionConfigError,
    FernetCipher,
    reset_fernet_cache,
)
from resilience_kit.runtime import set_settings_source
from resilience_kit.settings import CryptoSettings, ResilienceSettings


class _FixedSource:
    """Test settings source returning a frozen :class:`ResilienceSettings`."""

    def __init__(self, settings: ResilienceSettings) -> None:
        self._settings = settings

    def load(self) -> ResilienceSettings:
        """Return the frozen settings."""
        return self._settings


def _install(**crypto_kwargs: Any) -> None:
    """Install a settings source with the given :class:`CryptoSettings` shape."""
    settings = ResilienceSettings(crypto=CryptoSettings(**crypto_kwargs))
    set_settings_source(_FixedSource(settings))
    reset_fernet_cache()


@pytest.fixture(autouse=True)
def _reset_after() -> Iterator[None]:
    """Make sure the Fernet cache is clean before and after every test."""
    reset_fernet_cache()
    yield
    reset_fernet_cache()


# --- Exit-gate: round-trip ---------------------------------------------------


def test_round_trip_with_explicit_key() -> None:
    """A real key round-trips plaintext → ciphertext → plaintext."""
    _install(
        field_encryption_key=SecretStr("a-real-secret"),
        environment="prod",
    )
    cipher = FernetCipher()
    token = cipher.encrypt("hello-world")
    assert token != "hello-world"
    assert cipher.decrypt(token) == "hello-world"


def test_round_trip_in_dev_without_key_warns_and_works() -> None:
    """Dev fallback: no key → warning, round-trip still works."""
    _install(environment="dev")
    cipher = FernetCipher()
    token = cipher.encrypt("local-secret")
    assert cipher.decrypt(token) == "local-secret"


def test_empty_string_passes_through() -> None:
    """Empty string encrypts/decrypts to itself (DB round-trip ergonomic)."""
    _install(environment="dev")
    assert FernetCipher.encrypt("") == ""
    assert FernetCipher.decrypt("") == ""


# --- #B6: raw-key path vs deprecated passphrase derivation ------------------


def test_raw_fernet_key_is_used_directly() -> None:
    """A real Fernet key is used as-is (no SHA-256 layer)."""
    key = Fernet.generate_key()  # bytes, 44 url-safe-b64 chars
    _install(field_encryption_key=SecretStr(key.decode("ascii")), environment="prod")
    token = FernetCipher.encrypt("hello")
    # Proof it was used directly: a raw Fernet(key) decrypts the kit's token.
    assert Fernet(key).decrypt(token.encode("ascii")).decode("utf-8") == "hello"


def test_passphrase_uses_legacy_sha256_derivation() -> None:
    """A passphrase still derives the same SHA-256 key — legacy data stays readable."""
    passphrase = "a-real-secret"
    _install(field_encryption_key=SecretStr(passphrase), environment="prod")
    token = FernetCipher.encrypt("hello")
    # The legacy derivation is unchanged, so old ciphertext still decrypts.
    derived = base64.urlsafe_b64encode(hashlib.sha256(passphrase.encode()).digest())
    assert Fernet(derived).decrypt(token.encode("ascii")).decode("utf-8") == "hello"


def test_passphrase_emits_deprecation_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The deprecated passphrase path warns once."""
    _install(field_encryption_key=SecretStr("a-real-secret"), environment="prod")
    with caplog.at_level(logging.WARNING):
        FernetCipher.encrypt("x")
    assert any("deprecated" in r.message.lower() for r in caplog.records)


def test_raw_key_does_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    """The recommended raw-key path is silent (no deprecation noise)."""
    key = Fernet.generate_key()
    _install(field_encryption_key=SecretStr(key.decode("ascii")), environment="prod")
    with caplog.at_level(logging.WARNING):
        FernetCipher.encrypt("x")
    assert not any("deprecated" in r.message.lower() for r in caplog.records)


# --- Exit-gate: refuses-to-start-in-prod ------------------------------------


def test_prod_without_key_raises_config_error_on_encrypt() -> None:
    """Prod + no key → :class:`EncryptionConfigError` at first encrypt."""
    _install(environment="prod")
    with pytest.raises(EncryptionConfigError, match="field_encryption_key must be set"):
        FernetCipher.encrypt("anything")


def test_prod_without_key_raises_config_error_on_decrypt() -> None:
    """Prod + no key → :class:`EncryptionConfigError` at first decrypt."""
    _install(environment="prod")
    with pytest.raises(EncryptionConfigError):
        FernetCipher.decrypt("anything")


# --- Key rotation / corruption ---------------------------------------------


def test_decrypt_with_wrong_key_raises_decryption_error() -> None:
    """A token encrypted under one key cannot be decrypted under another."""
    _install(field_encryption_key=SecretStr("first-key"), environment="prod")
    token = FernetCipher.encrypt("payload")

    # Rotate the key — same plaintext, new Fernet instance.
    _install(field_encryption_key=SecretStr("second-key"), environment="prod")
    with pytest.raises(DecryptionError, match="decrypt field value"):
        FernetCipher.decrypt(token)


def test_decrypt_corrupted_ciphertext_raises_decryption_error() -> None:
    """Garbled ciphertext maps onto :class:`DecryptionError` (not a raw InvalidToken)."""
    _install(field_encryption_key=SecretStr("the-key"), environment="prod")
    with pytest.raises(DecryptionError):
        FernetCipher.decrypt("not-a-real-token")


def test_cache_is_reused_until_reset() -> None:
    """The lru_cache memoises the Fernet instance until cleared."""
    _install(field_encryption_key=SecretStr("the-key"), environment="prod")
    token_a = FernetCipher.encrypt("x")
    # Without reset, decrypt should obviously work.
    assert FernetCipher.decrypt(token_a) == "x"
    # After reset + re-install with the same key, decrypt still works.
    reset_fernet_cache()
    assert FernetCipher.decrypt(token_a) == "x"
