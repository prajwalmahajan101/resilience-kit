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
    """Ensure the fake-third-party distribution is importable for the test.

    CI workflows pre-install the fixture via ``uv pip install -e
    tests/fixtures/fake_third_party`` before invoking pytest. When run
    locally without that prep, this fixture installs it on the fly via
    ``uv`` (falling back to ``python -m pip``); a still-failing install
    skips the test rather than failing it — the CI matrix is the
    authoritative gate.
    """
    if _is_fixture_installed():
        return
    fixture_root = Path(__file__).parent.parent / "fixtures" / "fake_third_party"
    for cmd in (
        ["uv", "pip", "install", "-e", str(fixture_root)],
        [sys.executable, "-m", "pip", "install", "-e", str(fixture_root)],
    ):
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            importlib.invalidate_caches()
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    pytest.skip(
        "Could not install fake_third_party fixture; CI pre-installs it.",
    )


def test_builtin_resolves_when_no_entry_point_shadows_it() -> None:
    """A builtin resolves when no installed EP shares its name (step 4).

    The fake-third-party fixture registers ``fake`` — not ``memory`` —
    so the entry-point lookup (step 3) misses and the builtin fallback
    (step 4) returns ``InMemoryAsyncCache``. This does *not* prove a
    builtin beats a same-named EP; the opposite is true (see
    :func:`test_entry_point_shadows_same_named_builtin`).
    """
    instance = resolve_provider(
        group="resilience_kit.cache_backends",
        name="memory",
        builtins={"memory": InMemoryAsyncCache},
    )
    assert isinstance(instance, InMemoryAsyncCache)


def test_entry_point_shadows_same_named_builtin() -> None:
    """An installed EP shadows a builtin of the SAME name — the EP wins (#A3).

    Pins the precedence documented in ADR 0004 / ADR 0009 and implemented
    in ``_providers.py``: entry-point lookup (step 3) runs *before* the
    builtin fallback (step 4). Here both the installed fixture EP and the
    ``builtins`` map use the name ``fake``; resolution must return the
    fixture's ``FakeCache``, never the builtin ``InMemoryAsyncCache``.
    """
    from fake_third_party.cache import FakeCache  # noqa: PLC0415 — fixture import.

    instance = resolve_provider(
        group="resilience_kit.cache_backends",
        name="fake",
        builtins={"fake": InMemoryAsyncCache},
    )
    assert isinstance(instance, FakeCache)
    assert not isinstance(instance, InMemoryAsyncCache)


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
