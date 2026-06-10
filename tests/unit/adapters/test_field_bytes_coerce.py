"""Regression: encrypted ORM fields must coerce ``bytes`` → ``str`` before decrypt.

``FernetCipher.decrypt`` calls ``.encode("ascii")`` on its input, which
raises ``AttributeError`` on ``bytes``. Some Django backends / SQLAlchemy
dialects (psycopg ``bytea`` shims, asyncpg under certain encodings, raw
queries) hand the cipher text back as ``bytes``. Both adapters must
tolerate that without crashing.

See ISSUE-003 in `.code_review/code_review_issues.md`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("cryptography")

from resilience_kit.crypto import FernetCipher, reset_fernet_cache
from resilience_kit.runtime import set_settings_source
from resilience_kit.settings import CryptoSettings, ResilienceSettings

if TYPE_CHECKING:
    from collections.abc import Iterator


class _FixedSource:
    def __init__(self, settings: ResilienceSettings) -> None:
        self._settings = settings

    def load(self) -> ResilienceSettings:
        return self._settings


@pytest.fixture(autouse=True)
def _dev_key() -> Iterator[None]:
    set_settings_source(_FixedSource(ResilienceSettings(crypto=CryptoSettings(environment="test"))))
    reset_fernet_cache()
    yield
    reset_fernet_cache()


def _ciphertext() -> str:
    return FernetCipher.encrypt("the quick brown fox")


def test_django_encrypted_charfield_decrypts_bytes() -> None:
    pytest.importorskip("django")
    from resilience_kit.adapters.django.fields import EncryptedCharField  # noqa: PLC0415

    field = EncryptedCharField()
    cipher = _ciphertext().encode("ascii")
    assert isinstance(cipher, bytes)

    plaintext = field.from_db_value(cipher, expression=None, connection=None)
    assert plaintext == "the quick brown fox"


def test_django_encrypted_charfield_decrypts_bytearray() -> None:
    pytest.importorskip("django")
    from resilience_kit.adapters.django.fields import EncryptedCharField  # noqa: PLC0415

    field = EncryptedCharField()
    plaintext = field.from_db_value(
        bytearray(_ciphertext(), "ascii"), expression=None, connection=None
    )
    assert plaintext == "the quick brown fox"


def test_django_encrypted_charfield_passes_str_through() -> None:
    pytest.importorskip("django")
    from resilience_kit.adapters.django.fields import EncryptedCharField  # noqa: PLC0415

    field = EncryptedCharField()
    plaintext = field.from_db_value(_ciphertext(), expression=None, connection=None)
    assert plaintext == "the quick brown fox"


def test_django_encrypted_charfield_none_passthrough() -> None:
    pytest.importorskip("django")
    from resilience_kit.adapters.django.fields import EncryptedCharField  # noqa: PLC0415

    field = EncryptedCharField()
    assert field.from_db_value(None, expression=None, connection=None) is None


def test_fastapi_encrypted_string_decrypts_bytes() -> None:
    pytest.importorskip("sqlalchemy")
    from resilience_kit.adapters.fastapi.fields import EncryptedString  # noqa: PLC0415

    col: Any = EncryptedString()
    cipher = _ciphertext().encode("ascii")
    plaintext = col.process_result_value(cipher, dialect=None)
    assert plaintext == "the quick brown fox"


def test_fastapi_encrypted_string_passes_str_through() -> None:
    pytest.importorskip("sqlalchemy")
    from resilience_kit.adapters.fastapi.fields import EncryptedString  # noqa: PLC0415

    col: Any = EncryptedString()
    plaintext = col.process_result_value(_ciphertext(), dialect=None)
    assert plaintext == "the quick brown fox"


def test_fastapi_encrypted_string_none_passthrough() -> None:
    pytest.importorskip("sqlalchemy")
    from resilience_kit.adapters.fastapi.fields import EncryptedString  # noqa: PLC0415

    col: Any = EncryptedString()
    assert col.process_result_value(None, dialect=None) is None
