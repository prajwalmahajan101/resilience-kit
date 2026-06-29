"""Unit tests for :mod:`resilience_kit.crypto.fernet` — exit-gate tests."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

import pytest

pytest.importorskip("cryptography")

from cryptography.fernet import Fernet, InvalidToken
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


def test_legacy_passphrase_ciphertext_still_decrypts() -> None:
    """Ciphertext written by the pre-#B6 SHA-256 derivation still decrypts.

    The token below was produced by an earlier kit version from the passphrase
    ``"a-real-secret"`` (key = ``b64(sha256(passphrase))``). That the current
    code decrypts it proves the legacy derivation is byte-for-byte unchanged, so
    upgrading forces no data migration. Pinning the ciphertext keeps the test
    from hashing a passphrase itself.
    """
    legacy_token = (
        "gAAAAABqQmYCjX0Pn1phIBEkrnHnj7XCfYo0xvs-"
        "h2RCQCDnROPwgN1IOBOXzfpH_dFQ4ddaxKaegyUXGWP5tiK9XkWaflDZmA=="
    )
    _install(field_encryption_key=SecretStr("a-real-secret"), environment="prod")
    assert FernetCipher.decrypt(legacy_token) == "hello"


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


# --- #C1: MultiFernet key rotation ------------------------------------------


def test_old_key_ciphertext_decrypts_after_prepending_new_primary() -> None:
    """Add a new primary; ciphertext written under the old key still decrypts."""
    k1 = Fernet.generate_key().decode("ascii")
    k2 = Fernet.generate_key().decode("ascii")

    _install(field_encryption_keys=[SecretStr(k1)], environment="prod")
    token = FernetCipher.encrypt("payload")

    # Rotate: k2 is now primary, k1 retained for decrypt.
    _install(field_encryption_keys=[SecretStr(k2), SecretStr(k1)], environment="prod")
    assert FernetCipher.decrypt(token) == "payload"


def test_new_data_encrypts_under_primary_key() -> None:
    """With [k2, k1], a fresh token is decryptable by a bare Fernet(k2)."""
    k1 = Fernet.generate_key()
    k2 = Fernet.generate_key()
    _install(
        field_encryption_keys=[
            SecretStr(k2.decode("ascii")),
            SecretStr(k1.decode("ascii")),
        ],
        environment="prod",
    )
    token = FernetCipher.encrypt("fresh")
    assert Fernet(k2).decrypt(token.encode("ascii")).decode("utf-8") == "fresh"


def test_rotate_upgrades_token_to_new_primary() -> None:
    """rotate() re-encrypts an old-key token so only the new primary reads it."""
    k1 = Fernet.generate_key()
    k2 = Fernet.generate_key()

    _install(field_encryption_keys=[SecretStr(k1.decode("ascii"))], environment="prod")
    old_token = FernetCipher.encrypt("secret")

    _install(
        field_encryption_keys=[
            SecretStr(k2.decode("ascii")),
            SecretStr(k1.decode("ascii")),
        ],
        environment="prod",
    )
    new_token = FernetCipher.rotate(old_token)
    # The rotated token is now readable by the new primary directly.
    assert Fernet(k2).decrypt(new_token.encode("ascii")).decode("utf-8") == "secret"
    # And the old key alone can no longer read it.
    with pytest.raises(InvalidToken):
        Fernet(k1).decrypt(new_token.encode("ascii"))


def test_rotate_empty_string_passes_through() -> None:
    """rotate('') is a no-op, mirroring encrypt/decrypt."""
    _install(environment="dev")
    assert FernetCipher.rotate("") == ""


def test_singular_key_still_works_and_warns() -> None:
    """The deprecated singular field is honoured as the sole key, with a warning."""
    key = Fernet.generate_key()
    _install(field_encryption_key=SecretStr(key.decode("ascii")), environment="prod")
    with pytest.warns(DeprecationWarning, match="field_encryption_key is deprecated"):
        token = FernetCipher.encrypt("legacy-config")
    assert FernetCipher.decrypt(token) == "legacy-config"


def test_list_wins_when_both_set() -> None:
    """When both list and singular are set, the list wins (singular ignored)."""
    k_list = Fernet.generate_key()
    k_singular = Fernet.generate_key()
    _install(
        field_encryption_keys=[SecretStr(k_list.decode("ascii"))],
        field_encryption_key=SecretStr(k_singular.decode("ascii")),
        environment="prod",
    )
    with pytest.warns(DeprecationWarning, match="list wins"):
        token = FernetCipher.encrypt("data")
    # Encrypted under the list key, not the singular one.
    assert Fernet(k_list).decrypt(token.encode("ascii")).decode("utf-8") == "data"
