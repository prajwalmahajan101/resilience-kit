"""Provider-chain resolution test — installable third-party fixture (LLD §3).

The kit's provider chain
(:func:`resilience_kit._providers.resolve_provider`) resolves a backend
name through five steps; step 3 is *entry-point lookup*. This test
installs ``tests/fixtures/fake_third_party`` as a real distribution and
asserts that the kit discovers it via that step.

The install is performed *once* per session in :mod:`tests.conftest`'s
fixture (commit 18 wires CI to do the equivalent in the workflow); this
file only asserts the discovery.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from importlib.metadata import distributions
from pathlib import Path

import pytest

from resilience_kit._providers import resolve_provider
from resilience_kit.cache.memory_impl import InMemoryAsyncCache


def _is_fixture_installed() -> bool:
    return any(d.metadata["Name"] == "fake-third-party" for d in distributions())


@pytest.fixture(scope="module", autouse=True)
def _install_fixture() -> None:
    """Ensure the fake-third-party distribution is importable for the test."""
    if _is_fixture_installed():
        return
    fixture_root = Path(__file__).parent.parent / "fixtures" / "fake_third_party"
    # ``uv pip install`` works in uv-managed venvs (which lack a stand-alone
    # ``pip`` module); fall back to ``python -m pip`` when uv is not on PATH.
    try:
        subprocess.run(
            ["uv", "pip", "install", "-e", str(fixture_root)],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(fixture_root)],
            check=True,
            capture_output=True,
        )
    # Refresh importlib metadata cache so entry_points() sees the new dist.
    importlib.invalidate_caches()


def test_builtin_resolves_first() -> None:
    """A kit-shipped builtin (``memory``) wins over any same-named EP."""
    instance = resolve_provider(
        group="resilience_kit.cache_backends",
        name="memory",
        builtins={"memory": InMemoryAsyncCache},
    )
    assert isinstance(instance, InMemoryAsyncCache)


def test_entry_point_lookup_resolves_third_party() -> None:
    """A third-party EP under the kit's group is resolved by name."""
    from fake_third_party.cache import FakeCache  # noqa: PLC0415 — fixture import.

    instance = resolve_provider(
        group="resilience_kit.cache_backends",
        name="fake",
        builtins={"memory": InMemoryAsyncCache},
    )
    assert isinstance(instance, FakeCache)


def test_unknown_name_lists_available_options() -> None:
    """An unknown name fails with ``UnknownBackendError`` listing both EP and builtin names."""
    from resilience_kit.exceptions import UnknownBackendError  # noqa: PLC0415

    with pytest.raises(UnknownBackendError) as info:
        resolve_provider(
            group="resilience_kit.cache_backends",
            name="does-not-exist",
            builtins={"memory": InMemoryAsyncCache},
        )
    assert "fake" in info.value.available
    assert "memory" in info.value.available
