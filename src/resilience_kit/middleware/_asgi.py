"""Shared ASGI type aliases for the middleware package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, MutableMapping

    Scope = MutableMapping[str, Any]
    Message = MutableMapping[str, Any]
    Receive = Callable[[], Awaitable[Message]]
    Send = Callable[[Message], Awaitable[None]]
    App = Callable[[Scope, Receive, Send], Awaitable[None]]

__all__ = ["App", "Message", "Receive", "Scope", "Send"]
