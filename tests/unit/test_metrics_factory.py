"""Unit tests for the M4 settings-driven metrics-sink factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resilience_kit.metrics import (
    NoopMetricsSink,
    StdlibLoggingMetricsSink,
    get_metrics,
    reset_metrics,
    set_metrics,
)
from resilience_kit.runtime import set_settings_source
from resilience_kit.settings import ResilienceSettings

if TYPE_CHECKING:
    from collections.abc import Iterator


class _FixedSource:
    """Settings source returning a frozen instance."""

    def __init__(self, settings: ResilienceSettings) -> None:
        self._settings = settings

    def load(self) -> ResilienceSettings:
        """Return the frozen settings."""
        return self._settings


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    reset_metrics()
    yield
    reset_metrics()


def test_default_resolves_to_noop() -> None:
    """Default ``metrics_sink="noop"`` resolves to NoopMetricsSink."""
    set_settings_source(_FixedSource(ResilienceSettings(metrics_sink="noop")))
    assert isinstance(get_metrics(), NoopMetricsSink)


def test_stdlib_logging_resolves_from_settings() -> None:
    """``metrics_sink="stdlib_logging"`` builds the stdlib-logging sink."""
    set_settings_source(
        _FixedSource(ResilienceSettings(metrics_sink="stdlib_logging")),
    )
    assert isinstance(get_metrics(), StdlibLoggingMetricsSink)


def test_unknown_sink_falls_back_to_noop_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unknown sink name logs a warning and falls back to no-op."""
    set_settings_source(
        _FixedSource(ResilienceSettings(metrics_sink="does-not-exist")),
    )
    with caplog.at_level("WARNING"):
        sink = get_metrics()
    assert isinstance(sink, NoopMetricsSink)
    assert any("did not resolve" in rec.message for rec in caplog.records)


def test_set_metrics_wins_over_settings() -> None:
    """Explicit :func:`set_metrics` overrides the settings-driven default."""
    set_settings_source(
        _FixedSource(ResilienceSettings(metrics_sink="stdlib_logging")),
    )
    explicit = NoopMetricsSink()
    set_metrics(explicit)
    assert get_metrics() is explicit


def test_get_metrics_is_cached() -> None:
    """Repeated calls return the same sink instance."""
    set_settings_source(
        _FixedSource(ResilienceSettings(metrics_sink="stdlib_logging")),
    )
    assert get_metrics() is get_metrics()
