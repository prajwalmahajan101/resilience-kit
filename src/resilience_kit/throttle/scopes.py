"""Throttle scope key derivation — framework-agnostic.

Adapters (Django DRF, FastAPI deps) extract request attributes and pass them
through :func:`build_key`; the kit never imports from a web framework.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from resilience_kit.exceptions import ValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping


class Scope(StrEnum):
    """Throttle key scopes.

    ``IP``        — per-client IP.
    ``ENDPOINT``  — per-route.
    ``USER_TIER`` — per user.tier (caller maps users → tiers).
    ``GLOBAL``    — a single shared bucket across the whole service.
    ``BURST``     — secondary short-window bucket, distinct from the steady-state.
    ``AUTH``      — per-IP under the ``auth:`` namespace (login endpoints).
    """

    IP = "ip"
    ENDPOINT = "endpoint"
    USER_TIER = "user_tier"
    GLOBAL = "global"
    BURST = "burst"
    AUTH = "auth"


def build_key(scope: Scope, attrs: Mapping[str, str | None]) -> str:
    """Derive the throttle key for ``scope`` from caller-supplied attrs.

    Args:
        scope: Throttle scope.
        attrs: Required attributes per scope (see below). Missing or empty
            values raise :class:`ValidationError`.

            * ``IP``        — ``{"ip": <client-ip>}``
            * ``ENDPOINT``  — ``{"endpoint": <route-path>}``
            * ``USER_TIER`` — ``{"user_tier": <tier-name>}``
            * ``GLOBAL``    — *(no attrs required)*
            * ``BURST``     — ``{"ip": <client-ip>}``
            * ``AUTH``      — ``{"ip": <client-ip>}``

    Returns:
        A colon-delimited string suitable as a throttle key.

    Raises:
        ValidationError: A required attribute for ``scope`` is missing.
    """
    if scope is Scope.GLOBAL:
        return "throttle:global"
    if scope is Scope.IP:
        return f"throttle:ip:{_required(attrs, 'ip')}"
    if scope is Scope.ENDPOINT:
        return f"throttle:endpoint:{_required(attrs, 'endpoint')}"
    if scope is Scope.USER_TIER:
        return f"throttle:user_tier:{_required(attrs, 'user_tier')}"
    if scope is Scope.BURST:
        return f"throttle:burst:{_required(attrs, 'ip')}"
    if scope is Scope.AUTH:
        return f"throttle:auth:{_required(attrs, 'ip')}"
    raise ValidationError(f"Unhandled scope {scope!r}.", details={"scope": scope})


def _required(attrs: Mapping[str, str | None], key: str) -> str:
    value = attrs.get(key)
    if not value:
        raise ValidationError(
            f"Throttle scope requires attr {key!r}.",
            details={"missing_attr": key},
        )
    return value
