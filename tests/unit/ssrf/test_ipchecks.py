"""Unit tests for :mod:`resilience_kit.ssrf._ipchecks`."""

from __future__ import annotations

import pytest

from resilience_kit.ssrf._ipchecks import classify_non_public, is_non_public


@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        # Public unicast — must not classify.
        ("1.1.1.1", None),
        ("8.8.8.8", None),
        ("2001:4860:4860::8888", None),
        # Loopback.
        ("127.0.0.1", "loopback"),
        ("127.255.255.254", "loopback"),
        ("::1", "loopback"),
        # Link-local.
        ("169.254.1.1", "link_local"),
        ("fe80::1", "link_local"),
        # Multicast.
        ("224.0.0.1", "multicast"),
        ("ff02::1", "multicast"),
        # Unspecified.
        ("0.0.0.0", "unspecified"),
        ("::", "unspecified"),
        # Private (RFC1918 + RFC4193).
        ("10.0.0.1", "private"),
        ("172.16.0.1", "private"),
        ("192.168.1.1", "private"),
        ("fc00::1", "private"),
    ],
)
def test_classify_non_public(addr: str, expected: str | None) -> None:
    """Every non-public category is detected; public addresses are not."""
    assert classify_non_public(addr) == expected


@pytest.mark.parametrize(
    "addr",
    ["10.0.0.1", "127.0.0.1", "169.254.1.1", "224.0.0.1", "0.0.0.0", "::1"],
)
def test_is_non_public_true(addr: str) -> None:
    """All non-public categories collapse to ``True``."""
    assert is_non_public(addr) is True


@pytest.mark.parametrize("addr", ["1.1.1.1", "8.8.8.8", "2001:4860:4860::8888"])
def test_is_non_public_false(addr: str) -> None:
    """Routable public addresses are ``False``."""
    assert is_non_public(addr) is False


def test_invalid_address_raises_value_error() -> None:
    """Garbage in raises ``ValueError`` — never silently classified."""
    with pytest.raises(ValueError, match="does not appear"):
        classify_non_public("not-an-ip")
