"""Smoke tests — verify the package imports and exposes ``__version__``.

Real primitives are tested in dedicated suites under ``tests/unit/`` and
``tests/contract/`` from M1 onwards.
"""

from __future__ import annotations

import re

import resilience_kit


def test_package_imports() -> None:
    assert resilience_kit is not None


def test_version_is_pep440() -> None:
    # PEP 440 release segment (X.Y.Z) optionally followed by a pre/dev/post tag.
    assert re.match(
        r"^\d+\.\d+\.\d+([.+-]?(a|b|rc|dev|post)\d+)?$",
        resilience_kit.__version__,
    ), resilience_kit.__version__
