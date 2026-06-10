"""Unit tests for :func:`resilience_kit.testing.reset_all_singletons_async`."""

from __future__ import annotations

from resilience_kit.runtime import get_settings
from resilience_kit.testing import reset_all_singletons_async


async def test_reset_all_singletons_async_clears_state() -> None:
    # Warm the settings cache so we have a singleton to reset.
    before = get_settings()
    assert get_settings() is before  # cache hit

    await reset_all_singletons_async()

    # After reset, get_settings() rebuilds — identity differs.
    after = get_settings()
    assert after is not before
