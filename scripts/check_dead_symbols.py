#!/usr/bin/env python3
"""Fail when a public symbol under ``src/resilience_kit/`` has zero references.

Utility atrophy is low-grade entropy: a public ``def`` / ``class`` that
no longer has a caller lingers through review cycles. This script flags
the shape mechanically.

Ported from ``colending_partner/scripts/check_dead_utils.py`` and adapted
to this repo's layout:

* The package is a **flat** ``resilience_kit`` (``src``-layout), so the
  dotted import path is computed relative to ``src/`` —
  ``src/resilience_kit/cache/provider.py`` → ``resilience_kit.cache.provider``.
* ``SEARCH_ROOTS`` is ``src/`` **and** ``tests/`` — a symbol exercised by
  the test suite counts as live.
* A symbol re-exported through any ``__all__`` under the package counts as
  live. This is essential: the kit's public surface (decorators, protocols,
  exceptions) is consumed by external users and has no *internal* importer
  by design, so without this every public name would read as dead.

For each ``.py`` file under ``src/resilience_kit/`` (excluding
``__init__.py``) the script collects every public, top-level ``def`` /
``async def`` / ``class`` (no leading underscore) that is not referenced a
second time inside its own file, then asserts at least one of:

* it is imported (textually) from its dotted module path somewhere under
  ``SEARCH_ROOTS``; or
* its name appears in an ``__all__`` list in any package ``__init__.py``.

Exit codes:
    ``0`` — every public symbol is referenced.
    ``1`` — one or more dead symbols; their dotted paths are printed.

Run manually::

    uv run python scripts/check_dead_symbols.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCAN_ROOTS = [SRC / "resilience_kit"]
SEARCH_ROOTS = [SRC, ROOT / "tests"]

# Public (dotted_path, symbol) pairs intentionally exempt from the check.
# Add an entry only with a comment explaining why a public symbol has no
# importer and is not re-exported via ``__all__``.
ALLOWLIST: set[tuple[str, str]] = set()


def _module_dotted(path: Path) -> str:
    """Return the dotted import path for *path*, relative to ``src/``.

    Args:
        path: Absolute path to a source file under ``src/``.

    Returns:
        Dotted module path (e.g. ``resilience_kit.cache.provider``).
    """
    rel = path.resolve().relative_to(SRC).with_suffix("")
    return ".".join(rel.parts)


def _public_symbols(path: Path) -> list[str]:
    """Return public top-level names in *path* with no second in-file use.

    Args:
        path: Python source file.

    Returns:
        Names of public top-level ``def`` / ``async def`` / ``class``
        declarations referenced only once (the declaration) inside the
        file. Underscore-prefixed names are excluded.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            if source.count(node.name) < 2:
                names.append(node.name)
    return names


def _all_exported_names() -> set[str]:
    """Collect every name listed in an ``__all__`` under the package.

    Returns:
        The union of string literals assigned to ``__all__`` in any
        ``__init__.py`` beneath ``src/resilience_kit/``. A name here is
        part of the public surface and therefore live.
    """
    exported: set[str] = set()
    for init in SCAN_ROOTS[0].rglob("__init__.py"):
        tree = ast.parse(init.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                continue
            if isinstance(node.value, (ast.List, ast.Tuple)):
                exported.update(
                    elt.value
                    for elt in node.value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                )
    return exported


def _has_importer(dotted_path: str, symbol: str, self_path: Path) -> bool:
    """Return ``True`` if any file under ``SEARCH_ROOTS`` imports *symbol*.

    Accepts ``from <dotted_path> import <symbol>`` (incl. parenthesised
    multi-imports) and ``import <dotted_path>`` followed by ``.<symbol>``.
    The match is textual.

    Args:
        dotted_path: Defining module path.
        symbol: Public name defined in that module.
        self_path: Defining file, skipped so an in-file reference is not
            mistaken for an importer.

    Returns:
        ``True`` when at least one source file references the symbol.
    """
    from_form = f"from {dotted_path} import"
    import_form = f"import {dotted_path}"
    self_resolved = self_path.resolve()

    for root in SEARCH_ROOTS:
        for py_file in root.rglob("*.py"):
            if py_file.resolve() == self_resolved:
                continue
            text = py_file.read_text(encoding="utf-8")
            if from_form in text and symbol in text:
                return True
            if import_form in text and f".{symbol}" in text:
                return True
    return False


def main() -> int:
    """Walk ``SCAN_ROOTS``, report dead public symbols, return 0/1.

    Returns:
        ``0`` on a clean run, ``1`` when one or more dead symbols exist.
    """
    exported = _all_exported_names()
    dead: list[tuple[str, str]] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if path.name == "__init__.py":
                continue
            dotted = _module_dotted(path)
            for symbol in _public_symbols(path):
                if (dotted, symbol) in ALLOWLIST or symbol in exported:
                    continue
                if not _has_importer(dotted, symbol, path):
                    dead.append((dotted, symbol))

    if dead:
        print("Dead public symbols under src/resilience_kit/:", file=sys.stderr)
        for dotted, symbol in dead:
            print(f"  {dotted}.{symbol}", file=sys.stderr)
        print(
            "\nEither wire a caller in the same commit, delete the symbol, "
            "re-export it via __all__, or add (dotted_path, symbol) to "
            "ALLOWLIST in scripts/check_dead_symbols.py with a reason.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
