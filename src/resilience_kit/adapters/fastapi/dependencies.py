"""FastAPI dependency providers backed by kit primitives.

Two dependencies ship today:

* :func:`rate_limit` — a factory that returns a dependency callable
  enforcing a throttle. The scope is one of
  :class:`~resilience_kit.throttle.scopes.Scope`; the rate is a string
  like ``"60/min"`` parsed by
  :meth:`~resilience_kit.throttle.base.Rate.parse`. The default
  attribute extractor reads ``request.client.host`` for IP-scoped
  buckets and ``request.url.path`` for endpoint-scoped buckets; callers
  override via ``attr_from_request`` to plug in user-tier or
  authenticated-IP behaviour.

* :func:`request_id_dep` — returns the active request-id ContextVar
  value (seeded upstream by the :class:`~resilience_kit.middleware.request_id.RequestIdMiddleware`).
  Useful for handlers that need the id for outbound calls or structured
  logs without re-importing the ContextVar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resilience_kit.context import request_id
from resilience_kit.exceptions import MissingExtraError, RateLimitError
from resilience_kit.throttle.base import Rate
from resilience_kit.throttle.provider import get_throttle
from resilience_kit.throttle.scopes import Scope, build_key

try:
    from fastapi import (
        Request,  # noqa: TC002 — runtime use (FastAPI resolves the annotation at dependency-binding time).
    )
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("fastapi", "prajwal-resilience-kit[fastapi]") from exc

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    AttrExtractor = Callable[[Request], Mapping[str, str | None]]


def rate_limit(
    scope: Scope,
    rate: str,
    *,
    attr_from_request: AttrExtractor | None = None,
) -> Callable[[Request], Awaitable[None]]:
    """Build a FastAPI dependency that enforces a throttle.

    The dependency runs before the route handler. On allow it returns
    ``None``; on deny it raises :class:`RateLimitError`, which the
    adapter's exception handler converts into a 429 response with
    ``Retry-After`` + ``X-RateLimit-*`` headers.

    The rate string is parsed *once* at dependency build time so the
    regex work does not run per-request.

    Args:
        scope: Which throttle bucket to charge. See
            :class:`~resilience_kit.throttle.scopes.Scope` for the
            attribute each scope expects.
        rate: A rate spec like ``"60/min"`` parsed by
            :meth:`Rate.parse`. Malformed specs raise
            :class:`~resilience_kit.exceptions.ValidationError`
            immediately, not at request time.
        attr_from_request: Optional override that maps the incoming
            request to the attribute dict consumed by
            :func:`~resilience_kit.throttle.scopes.build_key`. If
            omitted, a built-in extractor handles ``IP``, ``ENDPOINT``,
            ``GLOBAL``, ``BURST``, ``AUTH``. ``USER_TIER`` always
            requires a custom extractor since the kit has no opinion on
            authentication.

    Returns:
        A coroutine function suitable for ``Depends(...)``.

    Example:
        >>> from fastapi import Depends, FastAPI
        >>> from resilience_kit.adapters.fastapi import rate_limit
        >>> from resilience_kit.throttle import Scope
        >>> app = FastAPI()
        >>> @app.get("/search", dependencies=[Depends(rate_limit(Scope.IP, "60/min"))])
        ... async def search() -> dict[str, str]:
        ...     return {"ok": "true"}
    """
    parsed = Rate.parse(rate)
    extractor = attr_from_request or _default_attrs

    async def _dep(request: Request) -> None:
        attrs = extractor(request)
        key = build_key(scope, attrs)
        throttle = get_throttle()
        decision = await throttle.check(key, parsed)
        if not decision.allowed:
            raise RateLimitError(
                limit=decision.limit,
                remaining=decision.remaining,
                reset_at=decision.reset_at,
                retry_after=decision.reset_after,
                scope=scope.value,
            )

    return _dep


def request_id_dep() -> str | None:
    """Return the active request id from the ContextVar.

    Returns:
        The request id seeded by
        :class:`~resilience_kit.middleware.request_id.RequestIdMiddleware`,
        or ``None`` if the middleware is not installed. Handlers that
        require a non-``None`` id should assert it themselves so the
        violation surfaces at the route, not deep inside the audit
        layer.
    """
    return request_id.get()


def _default_attrs(request: Request) -> Mapping[str, str | None]:
    """Built-in attribute extractor covering IP / ENDPOINT / GLOBAL / BURST / AUTH.

    USER_TIER deliberately returns ``None`` so callers using that scope
    without their own extractor see :class:`ValidationError` from
    :func:`build_key` instead of a silent fall-through.
    """
    client_ip = request.client.host if request.client else None
    return {
        "ip": client_ip,
        "endpoint": request.url.path,
        "user_tier": None,
    }


__all__ = ["rate_limit", "request_id_dep"]
