"""Backoff strategies for :func:`~resilience_kit.retry.retry`.

Three pure-function strategies. The default is :func:`decorrelated_jitter`
(AWS Architecture Blog — "Exponential Backoff and Jitter") which spreads
retries better than full jitter under high contention.
"""

from __future__ import annotations

import random


def constant_backoff(*, base_delay: float) -> float:
    """Return a fixed delay regardless of attempt number.

    Args:
        base_delay: Delay in seconds.

    Returns:
        ``base_delay``.
    """
    return base_delay


def exponential_backoff(
    *,
    attempt: int,
    base_delay: float,
    exponential_base: float,
    max_delay: float,
) -> float:
    """Return ``min(max_delay, base_delay * exponential_base ** attempt)``.

    Args:
        attempt: 0-indexed attempt number.
        base_delay: Initial delay.
        exponential_base: Growth factor.
        max_delay: Upper bound.

    Returns:
        Backoff in seconds.
    """
    return min(max_delay, base_delay * (exponential_base**attempt))


def decorrelated_jitter(
    *,
    previous_delay: float,
    base_delay: float,
    max_delay: float,
    rng: random.Random | None = None,
) -> float:
    """Decorrelated jitter — ``min(max_delay, U(base_delay, prev * 3))``.

    On the first call, pass ``previous_delay == base_delay`` so the formula
    degrades to ``U(base, 3*base)``.

    Args:
        previous_delay: The delay used on the previous attempt.
        base_delay: Lower bound for the uniform draw.
        max_delay: Upper bound on the returned value.
        rng: Optional injectable RNG (tests pass a seeded ``random.Random``).

    Returns:
        Backoff in seconds.
    """
    upper = max(base_delay, previous_delay * 3.0)
    drawn = (
        rng.uniform(base_delay, upper) if rng is not None else random.uniform(base_delay, upper)  # noqa: S311 — jitter, not crypto
    )
    return min(max_delay, drawn)
