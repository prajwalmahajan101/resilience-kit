"""SSRF guard contract — same behaviour across allow-list modes.

The kit's SSRF guard exposes two layers (private-IP rejection +
allow-list). This suite parametrises the allow-list shape so the same
input table proves the contract under each mode.
"""

from __future__ import annotations

import pytest

from resilience_kit.exceptions import ValidationError
from resilience_kit.runtime import set_settings_source
from resilience_kit.settings import ResilienceSettings, SSRFSettings
from resilience_kit.ssrf import assert_allowed_url


class _FixedSource:
    """Test settings source returning a frozen :class:`ResilienceSettings`."""

    def __init__(self, settings: ResilienceSettings) -> None:
        self._settings = settings

    def load(self) -> ResilienceSettings:
        """Return the frozen settings."""
        return self._settings


@pytest.fixture(
    params=[
        pytest.param(["*"], id="wildcard"),
        pytest.param([], id="empty"),
        pytest.param(["partner.example", ".sub.example"], id="strict-list"),
    ],
)
def allowlist(request: pytest.FixtureRequest) -> list[str]:
    """Install ``request.param`` as the allow-list and return it."""
    param: list[str] = list(request.param)
    settings = ResilienceSettings(ssrf=SSRFSettings(outbound_allowlist=param))
    set_settings_source(_FixedSource(settings))
    return param


def test_wildcard_or_empty_is_permissive(allowlist: list[str]) -> None:
    """``["*"]`` and ``[]`` admit every URL — historical behaviour preserved."""
    if allowlist not in ([], ["*"]):
        pytest.skip("only the permissive params apply")
    assert_allowed_url("https://anything-goes.example/")


def test_strict_list_admits_known_hosts(allowlist: list[str]) -> None:
    """An explicit list passes both exact and suffix-matching members."""
    if allowlist in ([], ["*"]):
        pytest.skip("strict-list-only check")
    assert_allowed_url("https://partner.example/")
    assert_allowed_url("https://a.b.sub.example/")
    assert_allowed_url("https://sub.example/")  # apex of .suffix entry


def test_strict_list_rejects_unknown_hosts(allowlist: list[str]) -> None:
    """An explicit list rejects hosts that are neither exact nor suffix matches."""
    if allowlist in ([], ["*"]):
        pytest.skip("strict-list-only check")
    with pytest.raises(ValidationError, match="not in outbound_allowlist"):
        assert_allowed_url("https://other.example/")
