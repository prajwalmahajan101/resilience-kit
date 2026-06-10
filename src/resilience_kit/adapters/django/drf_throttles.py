"""DRF throttle classes backed by the kit's :class:`AsyncThrottle`.

DRF (``rest_framework.throttling``) ships its own
:class:`SimpleRateThrottle` whose state lives in the Django cache. The
kit ships a stronger ``AsyncThrottle`` with atomic Lua-driven sliding
windows in Redis / Valkey, in-call recovery probes, and a uniform
``ThrottleDecision`` shape. The classes here delegate every call into
the kit's throttle so a DRF project gets the same semantics as the
FastAPI app, the ASGI middleware, and any other adapter — without
having to glue both.

Each class subclasses :class:`BaseThrottle` (not
:class:`SimpleRateThrottle`) because:

1. ``SimpleRateThrottle`` hard-codes its cache backend; we route to the
   kit's :func:`get_throttle` instead.
2. ``SimpleRateThrottle`` ties the rate spec to a settings dict shape
   that conflicts with the kit's ``Rate.parse`` semantics.

Rates default to ``RESILIENCE_THROTTLE_RATES`` in Django settings,
keyed by scope name (``ip``, ``user_tier``, ``endpoint``, ``burst``,
``auth``). Subclasses override ``rate`` for an instance-specific spec.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

from resilience_kit.exceptions import MissingExtraError, RateLimitError
from resilience_kit.throttle.base import Rate
from resilience_kit.throttle.provider import get_throttle
from resilience_kit.throttle.scopes import Scope, build_key

try:
    from rest_framework.throttling import BaseThrottle
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("django", "resilience-kit[django]") from exc

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rest_framework.request import Request
    from rest_framework.views import APIView


_DEFAULT_RATES: dict[str, str] = {
    "ip": "60/min",
    "user_tier": "120/min",
    "endpoint": "300/min",
    "burst": "10/sec",
    "auth": "5/min",
}


class _KitThrottle(BaseThrottle):  # type: ignore[misc]  # rest_framework untyped — see mypy.ini
    """Shared base: derive the key, call the kit throttle, store the decision."""

    scope: ClassVar[Scope]
    rate: str | None = None  # subclasses or instances may override.

    def __init__(self) -> None:
        """Resolve the rate spec from instance / settings / default."""
        from django.conf import settings as django_settings  # noqa: PLC0415

        configured: Mapping[str, str] = getattr(
            django_settings,
            "RESILIENCE_THROTTLE_RATES",
            {},
        )
        spec = self.rate or configured.get(self.scope.value) or _DEFAULT_RATES[self.scope.value]
        self._parsed_rate = Rate.parse(spec)
        self._retry_after: float = 0.0

    def allow_request(self, request: Request, view: APIView) -> bool:
        """Return ``True`` on allow; raise :class:`RateLimitError` on deny.

        Raising rather than returning False routes the deny through the
        kit's exception handler so the LLD §11 envelope + the canonical
        ``X-RateLimit-*`` headers reach the client. DRF's own
        :class:`Throttled` exception is bypassed.
        """
        attrs = self._attrs(request, view)
        key = build_key(self.scope, attrs)
        decision = asyncio.run(get_throttle().check(key, self._parsed_rate))
        if not decision.allowed:
            raise RateLimitError(
                limit=decision.limit,
                remaining=decision.remaining,
                reset_at=decision.reset_at,
                retry_after=decision.reset_after,
                scope=self.scope.value,
            )
        return True

    def wait(self) -> float | None:
        """Unused — :meth:`allow_request` raises instead of returning False."""
        return None

    def _attrs(
        self,
        request: Request,
        view: APIView,
    ) -> Mapping[str, str | None]:
        """Subclasses provide the scope-specific attribute dict."""
        return {}


class IPThrottle(_KitThrottle):
    """Per-client-IP throttle."""

    scope = Scope.IP

    def _attrs(self, request: Request, view: APIView) -> Mapping[str, str | None]:
        return {"ip": self.get_ident(request)}


class UserTierThrottle(_KitThrottle):
    """Per ``request.user.tier`` throttle (caller must populate the tier)."""

    scope = Scope.USER_TIER

    def _attrs(self, request: Request, view: APIView) -> Mapping[str, str | None]:
        user = getattr(request, "user", None)
        tier = getattr(user, "tier", None) if user is not None else None
        return {"user_tier": tier}


class EndpointThrottle(_KitThrottle):
    """Per-endpoint throttle keyed on the view's URL pattern."""

    scope = Scope.ENDPOINT

    def _attrs(self, request: Request, view: APIView) -> Mapping[str, str | None]:
        endpoint = getattr(view, "basename", None) or view.__class__.__name__
        return {"endpoint": endpoint}


class BurstThrottle(_KitThrottle):
    """Secondary short-window IP throttle, distinct from the steady-state."""

    scope = Scope.BURST

    def _attrs(self, request: Request, view: APIView) -> Mapping[str, str | None]:
        return {"ip": self.get_ident(request)}


class AuthThrottle(_KitThrottle):
    """Login / auth-route throttle — IP-scoped under the ``auth:`` namespace."""

    scope = Scope.AUTH

    def _attrs(self, request: Request, view: APIView) -> Mapping[str, str | None]:
        return {"ip": self.get_ident(request)}


__all__ = [
    "AuthThrottle",
    "BurstThrottle",
    "EndpointThrottle",
    "IPThrottle",
    "UserTierThrottle",
]
