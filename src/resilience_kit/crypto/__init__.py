"""Field-level Fernet encryption — requires the ``crypto`` extra.

Public surface:

* :class:`FernetCipher` — encrypt / decrypt strings round-trip.
* :class:`EncryptionConfigError` — missing key in a non-dev environment.
* :class:`FernetUnavailableError` — ``cryptography`` is not installed.
* :class:`DecryptionError` — re-exported from
  :mod:`resilience_kit.exceptions` for ergonomics.
"""

from __future__ import annotations

from resilience_kit.crypto.exceptions import (
    DecryptionError,
    EncryptionConfigError,
    FernetUnavailableError,
)
from resilience_kit.crypto.fernet import FernetCipher, reset_fernet_cache

__all__ = [
    "DecryptionError",
    "EncryptionConfigError",
    "FernetCipher",
    "FernetUnavailableError",
    "reset_fernet_cache",
]
