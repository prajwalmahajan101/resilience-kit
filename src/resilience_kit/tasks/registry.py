"""Name → coroutine registry for the fire-and-forget task queue."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    TaskHandler = Callable[..., Awaitable[Any]]


_lock = threading.Lock()
_handlers: dict[str, TaskHandler] = {}


def register(name: str) -> Callable[[TaskHandler], TaskHandler]:
    """Register a coroutine under ``name``.

    Use as a decorator::

        @register("send_email")
        async def send_email(*, to: str, body: str) -> None: ...

    Args:
        name: Lookup key for :func:`~resilience_kit.tasks.submit`.

    Returns:
        The decorator.

    Raises:
        ValueError: ``name`` is already registered (registration is
            idempotent only if the same handler object is passed).
    """

    def decorator(func: TaskHandler) -> TaskHandler:
        with _lock:
            existing = _handlers.get(name)
            if existing is not None and existing is not func:
                msg = f"Task handler {name!r} already registered."
                raise ValueError(msg)
            _handlers[name] = func
        return func

    return decorator


def get_handler(name: str) -> TaskHandler:
    """Return the handler registered under ``name``.

    Args:
        name: Registered task name.

    Returns:
        The coroutine function.

    Raises:
        KeyError: ``name`` is not registered.
    """
    handler = _handlers.get(name)
    if handler is None:
        msg = f"No task handler registered for {name!r}."
        raise KeyError(msg)
    return handler


def reset_registry() -> None:
    """Clear the handler registry — used by ``testing.reset``."""
    with _lock:
        _handlers.clear()


def all_handlers() -> dict[str, TaskHandler]:
    """Return a snapshot of the current registry (read-only mapping copy)."""
    with _lock:
        return dict(_handlers)


__all__ = ["all_handlers", "get_handler", "register", "reset_registry"]
