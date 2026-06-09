"""End-to-end behavioural test for ``@resilient`` — the M1 ROADMAP exit clause.

Proves the breaker-over-retry composition: retries happen inside one
breaker attempt, then the breaker opens on the next failure batch.
"""

from __future__ import annotations

import pytest

from resilience_kit import registry, resilient
from resilience_kit.exceptions import ServiceUnavailableError, TransientError


async def test_resilient_composes_retry_inside_breaker() -> None:
    registry.register_service(
        "flaky",
        {
            "retry": {"max_attempts": 3, "wait_min": 0.001, "wait_max": 0.001},
            "circuit_breaker": {"fail_max": 2},
        },
    )
    calls = 0

    @resilient("flaky")
    async def upstream() -> None:
        nonlocal calls
        calls += 1
        raise TransientError("boom")

    # First call: 3 retries → counts as 1 breaker failure.
    with pytest.raises(TransientError):
        await upstream()
    # Second call: 3 retries → 2nd breaker failure → breaker OPEN.
    with pytest.raises(TransientError):
        await upstream()
    # Third call: breaker short-circuits before retry runs.
    with pytest.raises(ServiceUnavailableError):
        await upstream()
    # Exactly 2 batches of 3 attempts; the OPEN call did not invoke upstream.
    assert calls == 6
