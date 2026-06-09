"""``@circuit_breaker`` and ``@resilient`` decorators.

``@circuit_breaker(name)`` wraps a callable in the per-service breaker.
``@resilient(name)`` composes ``circuit_breaker(retry(func))`` — **outer
breaker, inner retry**. The breaker decides whether to attempt the call;
the retry handles transient blips within an attempt. ``ServiceUnavailableError``
is filtered from retry's ``retry_on`` so a retried call cannot defeat the
breaker (see :mod:`resilience_kit.retry.decorator`).
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from resilience_kit.registry import registry as _registry
from resilience_kit.retry.decorator import retry_on_failure

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

P = ParamSpec("P")
T = TypeVar("T")


def circuit_breaker(service_name: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Wrap a callable in the per-service circuit breaker.

    Args:
        service_name: Service identifier registered (or auto-defaulted) in
            :data:`~resilience_kit.registry.registry`.

    Returns:
        The wrapping decorator.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        """Detect sync vs async and dispatch to the matching wrapper.

        Args:
            func: The callable being wrapped.

        Returns:
            The wrapped callable.
        """
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                """Resolve the breaker and dispatch (async path).

                Args:
                    *args: Positional arguments forwarded to ``func``.
                    **kwargs: Keyword arguments forwarded to ``func``.

                Returns:
                    Whatever the wrapped coroutine returned.
                """
                breaker = _registry.get_breaker(service_name)
                return await breaker.call(
                    cast("Callable[..., Awaitable[Any]]", func),
                    *args,
                    **kwargs,
                )

            return cast("Callable[P, T]", async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            """Sync entry — refuses to nest inside an existing event loop.

            Args:
                *args: Positional arguments forwarded to ``func``.
                **kwargs: Keyword arguments forwarded to ``func``.

            Returns:
                Whatever the wrapped function returned.

            Raises:
                RuntimeError: Called from within a running event loop —
                    the sync wrapper would create a nested loop. Callers
                    should use the async decorator on an async function.
            """
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                raise RuntimeError(
                    f"@circuit_breaker({service_name!r}) sync wrapper called inside a "
                    "running event loop. Apply the decorator to an async function instead.",
                )
            breaker = _registry.get_breaker(service_name)

            async def _runner() -> Any:
                return await breaker.call(_to_async(func), *args, **kwargs)

            return asyncio.run(_runner())

        return sync_wrapper

    return decorator


def resilient(service_name: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Compose ``circuit_breaker(retry(func))`` — the standard outbound wrap.

    Args:
        service_name: Service identifier.

    Returns:
        The wrapping decorator.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        """Apply retry (inner) and circuit breaker (outer) to ``func``.

        Args:
            func: The callable being wrapped.

        Returns:
            The wrapped callable.
        """
        retried = retry_on_failure(service_name)(func)
        return circuit_breaker(service_name)(retried)

    return decorator


def _to_async(func: Callable[P, T]) -> Callable[P, Awaitable[T]]:
    """Wrap a sync callable so the breaker can ``await`` it.

    Args:
        func: Sync callable.

    Returns:
        An async wrapper that runs ``func`` inline.
    """

    @functools.wraps(func)
    async def shim(*args: P.args, **kwargs: P.kwargs) -> T:
        return func(*args, **kwargs)

    return shim
