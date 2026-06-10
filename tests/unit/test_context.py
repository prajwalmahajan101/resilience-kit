"""Unit tests for :mod:`resilience_kit.context`."""

from __future__ import annotations

from contextvars import ContextVar

from resilience_kit.context import bind, bind_to, request_id


def test_bind_to_copies_request_id_into_target() -> None:
    target: ContextVar[str | None] = ContextVar("target_under_test", default=None)
    with bind(request_id_value="abc"), bind_to(target):
        assert target.get() == "abc"


def test_bind_to_restores_target_on_exit() -> None:
    target: ContextVar[str | None] = ContextVar("target_under_test", default="prior")
    token = request_id.set("abc")
    try:
        with bind_to(target):
            assert target.get() == "abc"
        assert target.get() == "prior"
    finally:
        request_id.reset(token)


def test_bind_to_is_noop_when_target_is_request_id() -> None:
    token = request_id.set("abc")
    try:
        with bind_to(request_id):
            assert request_id.get() == "abc"
        assert request_id.get() == "abc"
    finally:
        request_id.reset(token)


def test_bind_to_copies_none_when_request_id_unset() -> None:
    target: ContextVar[str | None] = ContextVar("target_under_test", default="prior")
    with bind_to(target):
        assert target.get() is None
    assert target.get() == "prior"
