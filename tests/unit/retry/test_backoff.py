"""Backoff strategies — pure-function tests."""

from __future__ import annotations

import random

import pytest

from resilience_kit.retry.backoff import (
    constant_backoff,
    decorrelated_jitter,
    exponential_backoff,
)


def test_constant_returns_base() -> None:
    assert constant_backoff(base_delay=1.5) == 1.5


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(0, 1.0), (1, 2.0), (2, 4.0), (3, 8.0)],
)
def test_exponential_doubles(attempt: int, expected: float) -> None:
    got = exponential_backoff(
        attempt=attempt, base_delay=1.0, exponential_base=2.0, max_delay=100.0
    )
    assert got == expected


def test_exponential_caps_at_max() -> None:
    got = exponential_backoff(attempt=10, base_delay=1.0, exponential_base=2.0, max_delay=5.0)
    assert got == 5.0


def test_decorrelated_jitter_bounded() -> None:
    rng = random.Random(42)
    prev = 1.0
    for _ in range(100):
        d = decorrelated_jitter(
            previous_delay=prev,
            base_delay=1.0,
            max_delay=20.0,
            rng=rng,
        )
        assert 1.0 <= d <= 20.0
        prev = d


def test_decorrelated_jitter_grows_on_average() -> None:
    rng = random.Random(0)
    # Many iterations starting from base; average should rise above base.
    prev = 1.0
    samples: list[float] = []
    for _ in range(500):
        d = decorrelated_jitter(
            previous_delay=prev,
            base_delay=1.0,
            max_delay=100.0,
            rng=rng,
        )
        samples.append(d)
        prev = d
    assert sum(samples) / len(samples) > 1.5
