"""Unit tests for :mod:`resilience_kit.ssrf.guard`."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from resilience_kit.exceptions import ValidationError
from resilience_kit.runtime import set_settings_source
from resilience_kit.settings import ResilienceSettings, SSRFSettings
from resilience_kit.ssrf.guard import (
    assert_allowed_url,
    assert_public_url,
    resolve_and_validate,
    safe_host,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class _FixedSettingsSource:
    """Test source returning an explicit settings instance."""

    def __init__(self, settings: ResilienceSettings) -> None:
        self._settings = settings

    def load(self) -> ResilienceSettings:
        """Return the fixed settings."""
        return self._settings


@pytest.fixture
def install_settings() -> Iterator[Any]:
    """Yield a helper that installs an SSRFSettings override for one test."""

    def _install(**ssrf_kwargs: Any) -> None:
        settings = ResilienceSettings(ssrf=SSRFSettings(**ssrf_kwargs))
        set_settings_source(_FixedSettingsSource(settings))

    return _install


# --- safe_host --------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/x?q=1", "example.com"),
        ("http://user:pw@example.com:8080/", "example.com"),
        ("not-a-url", "external service"),
    ],
)
def test_safe_host(url: str, expected: str) -> None:
    """``safe_host`` strips path/query and degrades to a constant on garbage."""
    assert safe_host(url) == expected


# --- resolve_and_validate ---------------------------------------------------


def test_resolve_and_validate_disabled_returns_empty(install_settings: Any) -> None:
    """``block_private_ips=False`` short-circuits — no resolution, no rejection."""
    install_settings(block_private_ips=False)
    assert resolve_and_validate("http://10.0.0.1/path") == set()


def test_resolve_and_validate_rejects_non_http_scheme(install_settings: Any) -> None:
    """``file://`` and friends are blocked outright."""
    install_settings()
    with pytest.raises(ValidationError, match="scheme"):
        resolve_and_validate("file:///etc/passwd")


def test_resolve_and_validate_rejects_missing_host(install_settings: Any) -> None:
    """A URL without a hostname is invalid."""
    install_settings()
    with pytest.raises(ValidationError, match="hostname"):
        resolve_and_validate("http:///path")


def test_resolve_and_validate_rejects_private_ip_literal(install_settings: Any) -> None:
    """Private IP literal is rejected without any DNS lookup."""
    install_settings()
    with pytest.raises(ValidationError, match="non-public"):
        resolve_and_validate("http://10.0.0.1/")


def test_resolve_and_validate_accepts_public_ip_literal(install_settings: Any) -> None:
    """Public IP literal resolves to itself and is returned."""
    install_settings()
    assert resolve_and_validate("https://1.1.1.1/") == {"1.1.1.1"}


def test_resolve_and_validate_rejects_mixed_private_resolution(
    install_settings: Any,
) -> None:
    """If *any* resolved address is non-public, the URL is rejected."""
    install_settings()

    def fake_getaddrinfo(
        host: str,
        port: int | str | None,
    ) -> list[tuple[Any, Any, Any, Any, tuple[Any, ...]]]:
        return [
            (socket.AF_INET, 0, 0, "", ("8.8.8.8", 0)),
            (socket.AF_INET, 0, 0, "", ("10.0.0.5", 0)),
        ]

    with (
        patch("resilience_kit.ssrf.guard.socket.getaddrinfo", fake_getaddrinfo),
        pytest.raises(ValidationError, match="non-public"),
    ):
        resolve_and_validate("https://partner.example/")


def test_resolve_and_validate_strict_false_swallows_dns_failure(
    install_settings: Any,
) -> None:
    """``strict=False`` returns an empty set when DNS fails."""
    install_settings()

    def fake_getaddrinfo(host: str, port: int | str | None) -> object:
        raise socket.gaierror("nope")

    with patch("resilience_kit.ssrf.guard.socket.getaddrinfo", fake_getaddrinfo):
        assert resolve_and_validate("https://nope.example/", strict=False) == set()


def test_resolve_and_validate_strict_true_raises_on_dns_failure(
    install_settings: Any,
) -> None:
    """``strict=True`` (default) turns DNS failure into ``ValidationError``."""
    install_settings()

    def fake_getaddrinfo(host: str, port: int | str | None) -> object:
        raise socket.gaierror("nope")

    with (
        patch("resilience_kit.ssrf.guard.socket.getaddrinfo", fake_getaddrinfo),
        pytest.raises(ValidationError, match="could not be resolved"),
    ):
        resolve_and_validate("https://nope.example/")


def test_assert_public_url_delegates(install_settings: Any) -> None:
    """``assert_public_url`` is a thin shim over ``resolve_and_validate``."""
    install_settings()
    with pytest.raises(ValidationError):
        assert_public_url("http://127.0.0.1/")


# --- assert_allowed_url -----------------------------------------------------


def test_allowlist_wildcard_permits_anything(install_settings: Any) -> None:
    """``["*"]`` (default) — anything goes."""
    install_settings(outbound_allowlist=["*"])
    assert_allowed_url("https://anything.example/")


def test_allowlist_empty_permits_anything(install_settings: Any) -> None:
    """Empty list is treated as permissive — matches historical behaviour."""
    install_settings(outbound_allowlist=[])
    assert_allowed_url("https://anything.example/")


def test_allowlist_exact_match(install_settings: Any) -> None:
    """Exact host match passes; sibling host does not."""
    install_settings(outbound_allowlist=["partner.example"])
    assert_allowed_url("https://partner.example/v1/x")
    with pytest.raises(ValidationError, match="not in outbound_allowlist"):
        assert_allowed_url("https://other.example/")


def test_allowlist_suffix_match(install_settings: Any) -> None:
    """``.partner.example`` matches the apex and any subdomain, nothing else."""
    install_settings(outbound_allowlist=[".partner.example"])
    assert_allowed_url("https://partner.example/")
    assert_allowed_url("https://api.partner.example/")
    assert_allowed_url("https://a.b.partner.example/")
    with pytest.raises(ValidationError):
        assert_allowed_url("https://evil-partner.example/")


def test_allowlist_rejects_missing_host(install_settings: Any) -> None:
    """No hostname in URL → reject (defensive — should never happen post-guard)."""
    install_settings(outbound_allowlist=["partner.example"])
    with pytest.raises(ValidationError, match="hostname"):
        assert_allowed_url("http:///path")
