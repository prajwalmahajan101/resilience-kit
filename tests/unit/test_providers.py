"""Provider-resolution chain (LLD §3)."""

from __future__ import annotations

import pytest

from resilience_kit._providers import resolve_provider
from resilience_kit.exceptions import UnknownBackendError


class _FakeBackend:
    """Test backend exposing a marker for identity checks."""

    def __init__(self, *, tag: str = "default") -> None:
        self.tag = tag


def test_explicit_instance_returned_as_is() -> None:
    inst = _FakeBackend(tag="explicit")
    got = resolve_provider(
        group="resilience_kit.cache_backends",
        name=inst,
        builtins={},
    )
    assert got is inst


def test_explicit_callable_invoked() -> None:
    got = resolve_provider(
        group="resilience_kit.cache_backends",
        name=_FakeBackend,
        builtins={},
        factory_kwargs={"tag": "callable"},
    )
    assert isinstance(got, _FakeBackend)
    assert got.tag == "callable"


def test_importable_string_resolves() -> None:
    got = resolve_provider(
        group="resilience_kit.cache_backends",
        name=f"{_FakeBackend.__module__}:_FakeBackend",
        builtins={},
        factory_kwargs={"tag": "imported"},
    )
    assert isinstance(got, _FakeBackend)
    assert got.tag == "imported"


def test_builtin_resolves() -> None:
    got = resolve_provider(
        group="resilience_kit.cache_backends",
        name="memfake",
        builtins={"memfake": lambda **kw: _FakeBackend(tag=kw.get("tag", "builtin"))},
        factory_kwargs={"tag": "from-builtin"},
    )
    assert got.tag == "from-builtin"


def test_unknown_backend_lists_available() -> None:
    with pytest.raises(UnknownBackendError) as excinfo:
        resolve_provider(
            group="resilience_kit.cache_backends",
            name="memcached",
            builtins={"memory": _FakeBackend, "redis": _FakeBackend},
        )
    assert excinfo.value.name == "memcached"
    assert "memory" in excinfo.value.available
    assert "redis" in excinfo.value.available


def test_importable_string_to_non_callable_raises_type_error() -> None:
    with pytest.raises(TypeError):
        resolve_provider(
            group="resilience_kit.cache_backends",
            name="resilience_kit:__version__",  # a string constant, not a class
            builtins={},
        )
