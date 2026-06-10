"""``MissingExtraError`` is raised at module-import time when an extra is absent."""

from __future__ import annotations

import builtins
import importlib
import sys

import pytest

from resilience_kit.exceptions import MissingExtraError


@pytest.mark.parametrize(
    "module_path",
    [
        "resilience_kit.circuit_breaker.redis_impl",
        "resilience_kit.throttle.redis_impl",
        "resilience_kit.cache.redis_impl",
    ],
)
def test_redis_modules_raise_when_redis_missing(
    module_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing ``redis`` from ``sys.modules`` makes the kit refuse to import the redis_impl."""
    # Drop the redis modules so the import inside the kit module fails.
    for mod in list(sys.modules):
        if mod == "redis" or mod.startswith("redis."):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    # Block any further import of ``redis`` by replacing __import__.
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "redis" or name.startswith("redis."):
            raise ImportError(f"simulated missing extra: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    # Drop the kit module so the import side-effect re-runs.
    monkeypatch.delitem(sys.modules, module_path, raising=False)
    with pytest.raises(MissingExtraError) as excinfo:
        importlib.import_module(module_path)
    assert excinfo.value.extra == "redis"
    assert "resilience-kit[redis]" in str(excinfo.value)
