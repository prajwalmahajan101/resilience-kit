"""Reset kit singletons between unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resilience_kit.testing import reset_all_singletons

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset_kit_singletons() -> Iterator[None]:
    """Reset all kit singletons around each test."""
    reset_all_singletons()
    yield
    reset_all_singletons()
