"""Guard tests for the Django middleware dispatch shape (#A2).

Django dispatches middleware through ``__call__`` (sync) or a
``markcoroutinefunction``-flagged ``__call__`` (async) — it has **no**
``__acall__`` hook. The kit's Django middleware are synchronous; under
ASGI Django adapts them via ``sync_to_async``. These tests pin that shape
so a stray ``async def __acall__`` (unreachable dead code) can't creep
back in.
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("django")

from resilience_kit.adapters.django import middleware

_MIDDLEWARE_CLASSES = [
    middleware.RequestIdMiddleware,
    middleware.BodyLimitMiddleware,
    middleware.SecurityHeadersMiddleware,
    middleware.SelectiveCorsMiddleware,
    middleware.RateLimitHeadersMiddleware,
    middleware.ExceptionLoggingMiddleware,
]


@pytest.mark.parametrize("cls", _MIDDLEWARE_CLASSES, ids=lambda c: c.__name__)
def test_no_unreachable_acall(cls: type) -> None:
    """No middleware defines ``__acall__`` — Django never dispatches it."""
    assert not hasattr(cls, "__acall__")


@pytest.mark.parametrize("cls", _MIDDLEWARE_CLASSES, ids=lambda c: c.__name__)
def test_call_is_synchronous(cls: type) -> None:
    """Dispatch is the sync ``__call__`` (Django wraps it under ASGI)."""
    assert not inspect.iscoroutinefunction(cls.__call__)
