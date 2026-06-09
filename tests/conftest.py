"""Global pytest fixtures.

The autouse :func:`_reset_kit_singletons` here covers smoke tests at the
top level; ``tests/unit`` and ``tests/contract`` keep their own (identical)
copies in their sub-conftests so test discovery in either folder alone
remains hermetic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resilience_kit.testing import reset_all_singletons

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset_kit_singletons() -> Iterator[None]:
    """Reset every kit-managed singleton between tests."""
    reset_all_singletons()
    yield
    reset_all_singletons()
