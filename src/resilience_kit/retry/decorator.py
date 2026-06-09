"""``@retry`` and ``@retry_on_failure`` — sync + async.

Two decorators:
  * :func:`retry` — explicit knobs, no registry coupling.
  * :func:`retry_on_failure` — reads per-service policy from the registry;
    pair with :func:`resilience_kit.decorators.circuit_breaker` via the
    :func:`resilience_kit.decorators.resilient` shorthand.

Jitter strategies live in :mod:`resilience_kit.retry.backoff`. The default
is decorrelated.

``ServiceUnavailableError`` is **always** filtered out of ``retry_on`` so a
retried call cannot defeat an OPEN breaker — even when ``@retry`` and
``@circuit_breaker`` are accidentally composed in the wrong order.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import random
import time
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from resilience_kit.exceptions import ServiceUnavailableError
from resilience_kit.metrics import get_metrics
from resilience_kit.registry import registry as _registry
from resilience_kit.retry.backoff import decorrelated_jitter, exponential_backoff

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def _filter_retry_on(
    exceptions: tuple[type[BaseException], ...],
) -> tuple[type[BaseException], ...]:
    """Drop :class:`ServiceUnavailableError` from a ``retry_on`` tuple.

    Args:
        exceptions: Caller-supplied retry-on classes.

    Returns:
        Same tuple minus any :class:`ServiceUnavailableError` subclass.
    """
    return tuple(
        e
        for e in exceptions
        if not (isinstance(e, type) and issubclass(e, ServiceUnavailableError))
    )


def retry(  # noqa: PLR0915 — single-function retry loop is easier to audit
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0,
    max_delay: float = 60.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    jitter: str = "decorrelated",
    raise_on_failure: bool = True,
    on_error: Callable[[BaseException, int], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorate a sync or async callable with retries.

    Args:
        max_attempts: Total attempts (initial + retries). ``3`` means 1 initial + 2 retries.
        base_delay: Initial backoff in seconds.
        exponential_base: Growth factor (only used for ``jitter='none'`` / ``'full'``).
        max_delay: Cap on any single delay.
        exceptions: Classes that trigger a retry. ``ServiceUnavailableError`` is
            silently filtered out.
        jitter: ``"none"`` / ``"full"`` (exponential * uniform[0,1]) / ``"decorrelated"``.
        raise_on_failure: When ``True`` re-raise the last exception after
            ``max_attempts``; when ``False`` return ``None``.
        on_error: Optional ``(exc, attempt)`` callback fired after each failure.

    Returns:
        The wrapping decorator.
    """
    safe_exceptions = _filter_retry_on(exceptions)

    def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: PLR0915
        """Pick the sync or async wrapper based on ``func``'s shape.

        Args:
            func: The callable being wrapped.

        Returns:
            The wrapped callable.
        """
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                """Run ``func`` with retries (async path).

                Args:
                    *args: Positional arguments forwarded to ``func``.
                    **kwargs: Keyword arguments forwarded to ``func``.

                Returns:
                    Whatever the wrapped coroutine returned.

                Raises:
                    BaseException: The last caught exception, after retries
                        are exhausted and ``raise_on_failure`` is True.
                """
                last_exc: BaseException | None = None
                prev_delay = base_delay
                for attempt in range(max_attempts):
                    try:
                        result = await func(*args, **kwargs)
                        if attempt > 0:
                            get_metrics().incr(
                                "retry.success",
                                tags={"func": func.__name__, "attempt": str(attempt + 1)},
                            )
                        return cast("T", result)
                    except safe_exceptions as exc:
                        last_exc = exc
                        if on_error:
                            try:
                                on_error(exc, attempt + 1)
                            except Exception:
                                logger.exception("retry on_error callback failed")
                        if attempt == max_attempts - 1:
                            break
                        delay = _next_delay(
                            jitter=jitter,
                            attempt=attempt,
                            previous_delay=prev_delay,
                            base_delay=base_delay,
                            exponential_base=exponential_base,
                            max_delay=max_delay,
                        )
                        prev_delay = delay
                        get_metrics().incr(
                            "retry.attempt",
                            tags={"func": func.__name__, "attempt": str(attempt + 1)},
                        )
                        logger.warning(
                            "'%s' failed (attempt %d/%d): %s — retrying in %.2fs",
                            func.__name__,
                            attempt + 1,
                            max_attempts,
                            exc,
                            delay,
                        )
                        await asyncio.sleep(delay)
                get_metrics().incr(
                    "retry.exhausted",
                    tags={"func": func.__name__, "attempts": str(max_attempts)},
                )
                if raise_on_failure and last_exc is not None:
                    raise last_exc
                return cast("T", None)

            return cast("Callable[P, T]", async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            """Run ``func`` with retries (sync path).

            Args:
                *args: Positional arguments forwarded to ``func``.
                **kwargs: Keyword arguments forwarded to ``func``.

            Returns:
                Whatever the wrapped function returned.

            Raises:
                BaseException: The last caught exception, after retries
                    are exhausted and ``raise_on_failure`` is True.
            """
            last_exc: BaseException | None = None
            prev_delay = base_delay
            for attempt in range(max_attempts):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        get_metrics().incr(
                            "retry.success",
                            tags={"func": func.__name__, "attempt": str(attempt + 1)},
                        )
                    return result
                except safe_exceptions as exc:
                    last_exc = exc
                    if on_error:
                        try:
                            on_error(exc, attempt + 1)
                        except Exception:
                            logger.exception("retry on_error callback failed")
                    if attempt == max_attempts - 1:
                        break
                    delay = _next_delay(
                        jitter=jitter,
                        attempt=attempt,
                        previous_delay=prev_delay,
                        base_delay=base_delay,
                        exponential_base=exponential_base,
                        max_delay=max_delay,
                    )
                    prev_delay = delay
                    get_metrics().incr(
                        "retry.attempt",
                        tags={"func": func.__name__, "attempt": str(attempt + 1)},
                    )
                    logger.warning(
                        "'%s' failed (attempt %d/%d): %s — retrying in %.2fs",
                        func.__name__,
                        attempt + 1,
                        max_attempts,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
            get_metrics().incr(
                "retry.exhausted",
                tags={"func": func.__name__, "attempts": str(max_attempts)},
            )
            if raise_on_failure and last_exc is not None:
                raise last_exc
            return cast("T", None)

        return sync_wrapper

    return decorator


def retry_on_failure(service_name: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorate a callable with the retry policy registered for ``service_name``.

    Policy is read lazily from
    :class:`~resilience_kit.registry.ResilienceRegistry` at call time, so
    callers can ``registry.register_service`` after the decorator runs.

    Args:
        service_name: Service identifier.

    Returns:
        The wrapping decorator.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        """Apply the registered policy at call time.

        Args:
            func: The callable being wrapped.

        Returns:
            The wrapped callable.
        """
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                """Async — build the retry decorator per-call from current policy.

                Args:
                    *args: Positional arguments forwarded to ``func``.
                    **kwargs: Keyword arguments forwarded to ``func``.

                Returns:
                    Whatever the wrapped coroutine returned.
                """
                cfg = _registry.get_config(service_name).retry
                wrapped = retry(
                    max_attempts=cfg.max_attempts,
                    base_delay=cfg.wait_min,
                    max_delay=cfg.wait_max,
                    exponential_base=cfg.exponential_base,
                    jitter=cfg.jitter,
                    exceptions=cfg.retry_on or (Exception,),
                )(func)
                return await cast("Callable[..., Awaitable[Any]]", wrapped)(*args, **kwargs)

            return cast("Callable[P, T]", async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            """Sync — build the retry decorator per-call from current policy.

            Args:
                *args: Positional arguments forwarded to ``func``.
                **kwargs: Keyword arguments forwarded to ``func``.

            Returns:
                Whatever the wrapped function returned.
            """
            cfg = _registry.get_config(service_name).retry
            wrapped = retry(
                max_attempts=cfg.max_attempts,
                base_delay=cfg.wait_min,
                max_delay=cfg.wait_max,
                exponential_base=cfg.exponential_base,
                jitter=cfg.jitter,
                exceptions=cfg.retry_on or (Exception,),
            )(func)
            return wrapped(*args, **kwargs)

        return sync_wrapper

    return decorator


def _next_delay(
    *,
    jitter: str,
    attempt: int,
    previous_delay: float,
    base_delay: float,
    exponential_base: float,
    max_delay: float,
) -> float:
    """Compute the next delay using the selected jitter strategy.

    Args:
        jitter: ``"none"`` / ``"full"`` / ``"decorrelated"``.
        attempt: 0-indexed attempt number.
        previous_delay: Delay used on the previous attempt.
        base_delay: Base / lower-bound delay.
        exponential_base: Growth factor.
        max_delay: Upper bound.

    Returns:
        Backoff in seconds.
    """
    if jitter == "none":
        return exponential_backoff(
            attempt=attempt,
            base_delay=base_delay,
            exponential_base=exponential_base,
            max_delay=max_delay,
        )
    if jitter == "full":
        capped = exponential_backoff(
            attempt=attempt,
            base_delay=base_delay,
            exponential_base=exponential_base,
            max_delay=max_delay,
        )
        return random.uniform(0.0, capped)  # noqa: S311 — jitter, not crypto
    # decorrelated jitter is the default strategy
    return decorrelated_jitter(
        previous_delay=previous_delay,
        base_delay=base_delay,
        max_delay=max_delay,
    )
