r"""Outbound HTTP authentication helpers — Bearer / Basic / HMAC.

Each helper is an :class:`httpx.Auth` subclass so it composes naturally
with :class:`httpx.AsyncClient(auth=...)` and per-request ``auth=``
overrides. The HMAC helper signs the canonical request line
(``<method>\\n<path>\\n<timestamp>\\n<body>``) with HMAC-SHA256 and
attaches ``X-Signature`` + ``X-Signature-Timestamp`` headers — a common
shape across partner APIs that need symmetric request signing.

This module imports :mod:`httpx`; importing it without the ``http`` extra
raises :class:`~resilience_kit.exceptions.MissingExtraError` at import
time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import TYPE_CHECKING

from resilience_kit.exceptions import MissingExtraError, ValidationError

if TYPE_CHECKING:
    from collections.abc import Generator

try:
    import httpx
except ImportError as exc:  # pragma: no cover - exercised by missing_extra test
    raise MissingExtraError("http", "resilience-kit[http]") from exc


class BearerAuth(httpx.Auth):
    """Attach an ``Authorization: Bearer <token>`` header to every request."""

    def __init__(self, token: str) -> None:
        """Initialise with the bearer token.

        Args:
            token: The opaque bearer token to send.

        Raises:
            ValidationError: ``token`` is empty.
        """
        if not token:
            raise ValidationError("BearerAuth requires a non-empty token.")
        self._token = token

    def auth_flow(
        self,
        request: httpx.Request,
    ) -> Generator[httpx.Request, httpx.Response, None]:
        """Inject the ``Authorization`` header and yield the request.

        Args:
            request: The outbound request being authenticated.

        Yields:
            The same request with the header set.
        """
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


class BasicAuth(httpx.BasicAuth):
    """RFC-7617 Basic auth — thin wrapper validating username/password are present."""

    def __init__(self, username: str, password: str) -> None:
        """Initialise with credentials.

        Args:
            username: Basic-auth username.
            password: Basic-auth password.

        Raises:
            ValidationError: Either field is empty.
        """
        if not username or not password:
            raise ValidationError(
                "BasicAuth requires both username and password.",
                details={"username_set": bool(username), "password_set": bool(password)},
            )
        super().__init__(username, password)


class HMACAuth(httpx.Auth):
    r"""HMAC-SHA256 request signing for partner APIs.

    Signs ``<METHOD>\\n<PATH>\\n<TIMESTAMP>\\n<BODY>`` with the shared
    secret and attaches:

    * ``X-Signature`` — base64-encoded HMAC-SHA256 digest
    * ``X-Signature-Timestamp`` — Unix seconds, integer string
    * ``X-Signature-Key-Id`` — optional key identifier (omitted when
      ``key_id`` is ``None``)

    Body is included verbatim — callers MUST pass a deterministic
    serialisation (e.g. ``json.dumps(..., sort_keys=True)``) if the
    upstream verifies byte-for-byte.
    """

    requires_request_body = True

    def __init__(
        self,
        secret: str | bytes,
        *,
        key_id: str | None = None,
        clock: object | None = None,
    ) -> None:
        """Initialise with the shared secret and optional key identifier.

        Args:
            secret: Shared HMAC secret. ``str`` is encoded as UTF-8.
            key_id: Optional key identifier sent as ``X-Signature-Key-Id``.
            clock: Optional injectable clock — any object with a ``time()``
                method returning Unix seconds. Defaults to :mod:`time`.
                Used by tests to make signatures deterministic.

        Raises:
            ValidationError: ``secret`` is empty.
        """
        if not secret:
            raise ValidationError("HMACAuth requires a non-empty secret.")
        self._secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        self._key_id = key_id
        self._clock = clock if clock is not None else time

    def auth_flow(
        self,
        request: httpx.Request,
    ) -> Generator[httpx.Request, httpx.Response, None]:
        """Compute the signature for ``request`` and attach the headers.

        Args:
            request: The outbound request being signed.

        Yields:
            The same request with signature headers set.
        """
        timestamp = str(int(self._clock.time()))  # type: ignore[attr-defined]
        path = request.url.raw_path.decode("ascii")
        body = request.content
        canonical = b"\n".join(
            [
                request.method.encode("ascii"),
                path.encode("ascii"),
                timestamp.encode("ascii"),
                body,
            ],
        )
        digest = hmac.new(self._secret, canonical, hashlib.sha256).digest()
        request.headers["X-Signature"] = base64.b64encode(digest).decode("ascii")
        request.headers["X-Signature-Timestamp"] = timestamp
        if self._key_id is not None:
            request.headers["X-Signature-Key-Id"] = self._key_id
        yield request


__all__ = ["BasicAuth", "BearerAuth", "HMACAuth"]
