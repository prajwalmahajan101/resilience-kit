"""``@log_inbound`` / ``@log_outbound`` decorators (ROADMAP M4).

Both decorate sync + async callables. They capture timing, outcome,
and exception detail; build an :class:`AuditEvent`; and hand it to
the configured dispatcher. They never raise — audit failure must
never break a request.

Use:

* ``@log_inbound("api", method="POST", path="/v1/create")`` on a view.
* ``@log_outbound("partner", method="GET", path="/v1/x")`` on an
  outbound helper. (The HTTP client (M3) emits its own events directly
  via its ``on_outbound`` hook; this decorator is for non-HTTP RPC
  helpers and callers who want a uniform shape.)
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from resilience_kit.audit.backends.base import AuditEvent
from resilience_kit.audit.factory import get_dispatcher
from resilience_kit.context import correlation_id, request_id

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

_logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def log_inbound(
    service: str,
    *,
    method: str = "",
    path: str = "",
    payload_factory: Callable[..., Mapping[str, Any]] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Capture an inbound audit event around the decorated callable.

    Args:
        service: Service name (your service, the one receiving the
            request).
        method: Request method label — usually the HTTP verb.
        path: Request path label — usually the URL path.
        payload_factory: Optional callable receiving the decorated
            function's ``(args, kwargs)`` and returning a payload mapping
            for the audit event. Useful when the decorated function
            already takes parsed objects rather than raw payloads.

    Returns:
        The decorator.
    """
    return _make_decorator(
        direction="inbound",
        service=service,
        method=method,
        path=path,
        payload_factory=payload_factory,
    )


def log_outbound(
    service: str,
    *,
    method: str = "",
    path: str = "",
    payload_factory: Callable[..., Mapping[str, Any]] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Capture an outbound audit event around the decorated callable.

    See :func:`log_inbound`. Reserved for non-HTTP outbound paths;
    HTTP outbound is captured by :class:`~resilience_kit.http_client.AsyncAPIClient`'s
    own ``on_outbound`` hook.

    Args:
        service: Target service name.
        method: Request method label.
        path: Request path label.
        payload_factory: Optional payload extractor.

    Returns:
        The decorator.
    """
    return _make_decorator(
        direction="outbound",
        service=service,
        method=method,
        path=path,
        payload_factory=payload_factory,
    )


def _make_decorator(
    *,
    direction: str,
    service: str,
    method: str,
    path: str,
    payload_factory: Callable[..., Mapping[str, Any]] | None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if asyncio.iscoroutinefunction(func):
            return cast("Callable[P, T]", _wrap_async(func))
        return _wrap_sync(func)

    def _wrap_async(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def inner(*args: P.args, **kwargs: P.kwargs) -> T:
            started = time.monotonic()
            error_class: str | None = None
            error_code: str | None = None
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                error_class = type(exc).__name__
                error_code = getattr(exc, "error_code", None)
                _emit(
                    direction=direction,
                    service=service,
                    method=method,
                    path=path,
                    outcome="failure",
                    latency_ms=(time.monotonic() - started) * 1000,
                    error_class=error_class,
                    error_code=error_code,
                    payload=_extract_payload(payload_factory, args, kwargs),
                )
                raise
            _emit(
                direction=direction,
                service=service,
                method=method,
                path=path,
                outcome="success",
                latency_ms=(time.monotonic() - started) * 1000,
                payload=_extract_payload(payload_factory, args, kwargs),
            )
            return result

        return inner

    def _wrap_sync(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def inner(*args: P.args, **kwargs: P.kwargs) -> T:
            started = time.monotonic()
            error_class: str | None = None
            error_code: str | None = None
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                error_class = type(exc).__name__
                error_code = getattr(exc, "error_code", None)
                _emit(
                    direction=direction,
                    service=service,
                    method=method,
                    path=path,
                    outcome="failure",
                    latency_ms=(time.monotonic() - started) * 1000,
                    error_class=error_class,
                    error_code=error_code,
                    payload=_extract_payload(payload_factory, args, kwargs),
                )
                raise
            _emit(
                direction=direction,
                service=service,
                method=method,
                path=path,
                outcome="success",
                latency_ms=(time.monotonic() - started) * 1000,
                payload=_extract_payload(payload_factory, args, kwargs),
            )
            return result

        return inner

    return decorator


def _extract_payload(
    factory: Callable[..., Mapping[str, Any]] | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Mapping[str, Any]:
    if factory is None:
        return {}
    try:
        return factory(*args, **kwargs)
    except Exception:
        _logger.exception("audit payload_factory raised; substituting empty payload.")
        return {}


def _emit(
    *,
    direction: str,
    service: str,
    method: str,
    path: str,
    outcome: str,
    latency_ms: float,
    payload: Mapping[str, Any],
    error_class: str | None = None,
    error_code: str | None = None,
) -> None:
    event = AuditEvent(
        direction=direction,  # type: ignore[arg-type]
        service=service,
        method=method,
        path=path,
        outcome=outcome,  # type: ignore[arg-type]
        latency_ms=latency_ms,
        error_class=error_class,
        error_code=error_code,
        request_id=request_id.get(),
        correlation_id=correlation_id.get(),
        payload=payload,
    )
    try:
        get_dispatcher().submit(event)
    except Exception:
        _logger.exception("audit dispatch raised; event dropped.")


# Imported lazily by tests; not part of the runtime path.
_ = inspect

__all__ = ["log_inbound", "log_outbound"]
