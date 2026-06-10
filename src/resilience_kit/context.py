"""Request-scoped context vars — ``request_id`` and ``correlation_id``.

ContextVars are the kit's cross-cutting bus (LLD §9). They survive ``await``
boundaries within a task and are isolated across tasks. Adapters seed them
from inbound headers; the audit decorators read them when emitting events;
the DNS-pin in M3 lives in the same family.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

#: Inbound-request identifier (always per-process generated unless seeded by an adapter).
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

#: Cross-service correlation identifier (typically propagated from a header).
correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_request_id() -> str:
    """Return a fresh 32-character lowercase-hex request id.

    Returns:
        A URL-safe identifier suitable for logging and downstream propagation.
    """
    return uuid.uuid4().hex


@contextmanager
def bind(
    *,
    request_id_value: str | None = None,
    correlation_id_value: str | None = None,
) -> Iterator[None]:
    """Bind the supplied context vars for the duration of the ``with`` block.

    Passing ``None`` for a field leaves that var alone. Restores prior values
    on exit (works correctly under nesting and across ``await``).

    Args:
        request_id_value: Value to set into :data:`request_id`, or ``None``.
        correlation_id_value: Value to set into :data:`correlation_id`, or ``None``.

    Yields:
        Nothing — used purely for its side effect on the ContextVars.
    """
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    if request_id_value is not None:
        tokens.append((request_id, request_id.set(request_id_value)))
    if correlation_id_value is not None:
        tokens.append((correlation_id, correlation_id.set(correlation_id_value)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


@contextmanager
def bind_to(target: ContextVar[str | None]) -> Iterator[None]:
    """Mirror :data:`request_id` into ``target`` for the duration of the block.

    Lets a consumer's own ContextVar (e.g. a boilerplate's
    ``core.context.request_id_ctx``) receive whatever the kit's middleware
    seeded, so the consumer's logging / observability stack reads the same id
    without rewriting their own context layer.

    If ``target`` is :data:`request_id` itself, this is a no-op.

    Args:
        target: A ContextVar the caller owns and wants populated with the
            current kit ``request_id`` value inside the block.

    Yields:
        Nothing — used purely for its side effect on ``target``.
    """
    if target is request_id:
        yield
        return
    token = target.set(request_id.get())
    try:
        yield
    finally:
        target.reset(token)
