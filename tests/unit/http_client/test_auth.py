"""Unit tests for :mod:`resilience_kit.http_client.auth`."""

from __future__ import annotations

import base64
import hashlib
import hmac

import pytest

pytest.importorskip("httpx")

import httpx

from resilience_kit.exceptions import ValidationError
from resilience_kit.http_client.auth import BasicAuth, BearerAuth, HMACAuth


class _FrozenClock:
    """Injectable clock returning a fixed Unix-seconds value."""

    def __init__(self, value: float) -> None:
        self._value = value

    def time(self) -> float:
        """Return the frozen value."""
        return self._value


def _apply(auth: httpx.Auth, request: httpx.Request) -> httpx.Request:
    """Run ``auth.auth_flow`` once and return the resulting request."""
    flow = auth.auth_flow(request)
    return next(iter(flow))


# --- BearerAuth -------------------------------------------------------------


def test_bearer_sets_authorization() -> None:
    """Bearer attaches ``Authorization: Bearer <token>``."""
    req = httpx.Request("GET", "https://x.example/")
    out = _apply(BearerAuth("tok-123"), req)
    assert out.headers["Authorization"] == "Bearer tok-123"


def test_bearer_rejects_empty_token() -> None:
    """Empty token is a configuration error."""
    with pytest.raises(ValidationError, match="non-empty"):
        BearerAuth("")


# --- BasicAuth --------------------------------------------------------------


def test_basic_auth_sets_authorization() -> None:
    """Basic encodes username:password via the stdlib mechanism."""
    req = httpx.Request("GET", "https://x.example/")
    out = _apply(BasicAuth("alice", "s3cret"), req)
    assert out.headers["Authorization"].startswith("Basic ")
    decoded = base64.b64decode(out.headers["Authorization"].removeprefix("Basic ")).decode()
    assert decoded == "alice:s3cret"


@pytest.mark.parametrize(
    ("username", "password"),
    [("", "p"), ("u", ""), ("", "")],
)
def test_basic_auth_rejects_empty_credentials(username: str, password: str) -> None:
    """Both fields are required."""
    with pytest.raises(ValidationError, match="username and password"):
        BasicAuth(username, password)


# --- HMACAuth ---------------------------------------------------------------


def test_hmac_signs_canonical_request() -> None:
    """Signature == HMAC-SHA256(secret, METHOD\\nPATH\\nTS\\nBODY)."""
    secret = b"shhh"
    auth = HMACAuth(secret, clock=_FrozenClock(1_700_000_000.0))
    req = httpx.Request(
        "POST",
        "https://x.example/v1/sign?a=1",
        content=b'{"k":"v"}',
    )
    out = _apply(auth, req)

    expected_canonical = b"POST\n/v1/sign?a=1\n1700000000\n" + b'{"k":"v"}'
    expected = base64.b64encode(
        hmac.new(secret, expected_canonical, hashlib.sha256).digest(),
    ).decode()

    assert out.headers["X-Signature"] == expected
    assert out.headers["X-Signature-Timestamp"] == "1700000000"
    assert "X-Signature-Key-Id" not in out.headers


def test_hmac_attaches_key_id_when_provided() -> None:
    """``X-Signature-Key-Id`` is set when ``key_id`` is supplied."""
    auth = HMACAuth("shhh", key_id="k-1", clock=_FrozenClock(1.0))
    req = httpx.Request("GET", "https://x.example/")
    out = _apply(auth, req)
    assert out.headers["X-Signature-Key-Id"] == "k-1"


def test_hmac_rejects_empty_secret() -> None:
    """Empty secret is a configuration error."""
    with pytest.raises(ValidationError, match="non-empty"):
        HMACAuth("")


def test_hmac_accepts_str_or_bytes_secret() -> None:
    """``str`` secret is UTF-8 encoded; ``bytes`` is used verbatim."""
    auth_a = HMACAuth("shhh", clock=_FrozenClock(1.0))
    auth_b = HMACAuth(b"shhh", clock=_FrozenClock(1.0))
    req = httpx.Request("GET", "https://x.example/")
    assert (
        _apply(auth_a, httpx.Request("GET", "https://x.example/")).headers["X-Signature"]
        == _apply(auth_b, req).headers["X-Signature"]
    )
