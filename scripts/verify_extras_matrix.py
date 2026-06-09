#!/usr/bin/env python3
"""Install each declared extra in a clean virtualenv and import the package.

Used in CI to prove that:
  1. Every extra resolves to a valid set of dependencies.
  2. ``import resilience_kit`` works regardless of which extras are present.

The matrix is read from ``pyproject.toml`` so this script never needs to be
updated when a new extra is added.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


def main() -> int:
    """Iterate every declared extra, install it in a fresh venv, import the package."""
    pyproject = tomllib.loads(PYPROJECT.read_text())
    extras = list(pyproject["project"].get("optional-dependencies", {}))
    extras = [e for e in extras if e != "all"]

    failures: list[str] = []

    for extra in [None, *extras, "all"]:
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / ".venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
            pip = venv / "bin" / "pip"
            python = venv / "bin" / "python"

            target = str(ROOT) if extra is None else f"{ROOT}[{extra}]"
            label = "<no extras>" if extra is None else f"[{extra}]"
            print(f"\n=== verifying {label} ===", flush=True)

            try:
                subprocess.run(
                    [str(pip), "install", "--quiet", target],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    [str(python), "-c", "import resilience_kit; print(resilience_kit.__version__)"],
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                failures.append(label)
                print(f"FAILED {label}: {exc}", file=sys.stderr)
                if exc.stdout:
                    sys.stderr.write(exc.stdout.decode())
                if exc.stderr:
                    sys.stderr.write(exc.stderr.decode())

    if failures:
        print(f"\n{len(failures)} extras failed: {failures}", file=sys.stderr)
        return 1

    print("\nAll extras installed and imported cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
