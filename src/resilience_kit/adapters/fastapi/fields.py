"""SQLAlchemy 2.x ``EncryptedString`` over :class:`FernetCipher`.

A ``TypeDecorator`` is the SQLAlchemy-blessed extension point for
"this column stores X on disk and Y in Python." :class:`EncryptedString`
plain-text-in / cipher-text-out maps to the kit's
:class:`~resilience_kit.crypto.fernet.FernetCipher`, which derives its
key from :class:`~resilience_kit.settings.CryptoSettings` and refuses
to start in ``environment="prod"`` without an explicit
``field_encryption_key``.

The column type is ``String`` (variable-length text). Fernet tokens are
base64-url and grow predictably with plaintext length, so callers who
need a tight column bound pass ``length=`` and the constraint is
applied to the cipher text (not the plaintext).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.crypto.fernet import FernetCipher
from resilience_kit.exceptions import MissingExtraError

try:
    from sqlalchemy import String, TypeDecorator
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("fastapi", "resilience-kit[fastapi]") from exc

if TYPE_CHECKING:
    from sqlalchemy.engine.interfaces import Dialect


class EncryptedString(TypeDecorator[str]):
    """Transparent at-rest encryption for ``str`` columns.

    On ``INSERT`` / ``UPDATE`` the bound value is run through
    :meth:`FernetCipher.encrypt`. On ``SELECT`` the stored cipher text
    is run through :meth:`FernetCipher.decrypt`. ``None`` is passed
    through unchanged so ``NULL`` columns stay ``NULL``.

    Attributes:
        impl: ``String`` — the underlying column type SQLAlchemy emits
            in DDL.
        cache_ok: ``True`` — the type is value-stable so SQLAlchemy can
            cache compiled statements that reference it.
    """

    impl = String
    cache_ok = True

    def process_bind_param(
        self,
        value: str | None,
        dialect: Dialect,
    ) -> str | None:
        """Encrypt ``value`` before it hits the database."""
        if value is None:
            return None
        return FernetCipher.encrypt(value)

    def process_result_value(
        self,
        value: Any,
        dialect: Dialect,
    ) -> str | None:
        """Decrypt ``value`` on the way out of the database."""
        if value is None:
            return None
        return FernetCipher.decrypt(value)


__all__ = ["EncryptedString"]
