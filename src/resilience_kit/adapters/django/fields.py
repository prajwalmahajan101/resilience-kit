"""Django ORM ``EncryptedCharField`` over :class:`FernetCipher`.

Mirrors the FastAPI adapter's ``EncryptedString`` SQLAlchemy field.
``get_prep_value`` encrypts before the value hits the DB;
``from_db_value`` decrypts on read. ``None`` is passed through unchanged
so ``null=True`` columns stay ``NULL``.

The default ``max_length`` is 512 (Fernet tokens grow predictably with
plaintext length); callers tune per-column.
"""

from __future__ import annotations

from typing import Any

from resilience_kit.crypto.fernet import FernetCipher
from resilience_kit.exceptions import MissingExtraError

try:
    from django.db import models
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("django", "resilience-kit[django]") from exc


class EncryptedCharField(models.CharField):  # type: ignore[misc]  # django.db.models untyped
    """``CharField`` whose values are transparently Fernet-encrypted at rest.

    ``Field.get_prep_value`` and ``Field.from_db_value`` are the
    documented Django hook points for "convert Python ↔ DB". The
    encrypt / decrypt round-trip lives there so admin, ORM, raw queries
    via ``.values()``, and serialization all see plaintext while the
    column on disk holds the cipher.
    """

    description = "CharField with transparent Fernet encryption."

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Default max_length to 512 unless the caller overrides."""
        kwargs.setdefault("max_length", 512)
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value: Any) -> Any:
        """Encrypt ``value`` before it hits the database."""
        if value is None:
            return None
        return FernetCipher.encrypt(str(value))

    def from_db_value(
        self,
        value: Any,
        expression: Any,
        connection: Any,
    ) -> Any:
        """Decrypt ``value`` on the way out of the database.

        Django's CharField hands back ``str`` under normal conditions,
        but some backends / encodings (e.g. ``BinaryField`` migrations,
        custom drivers, raw queries) can return ``bytes``. Coerce at
        the boundary so :meth:`FernetCipher.decrypt` — which calls
        ``.encode("ascii")`` on its input — never raises
        ``AttributeError``.
        """
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            value = bytes(value).decode("ascii")
        return FernetCipher.decrypt(value)


__all__ = ["EncryptedCharField"]
