"""Starlette-friendly re-exports of the kit's ASGI middleware.

Starlette (and therefore FastAPI) accepts any ASGI3 callable via
``app.add_middleware(cls, **opts)`` — the kit's six middleware classes
already satisfy that shape, so this module exists only to:

* give adopters a single import path
  (``from resilience_kit.adapters.fastapi.middleware import ...``); and
* provide :func:`install_middleware_stack` — a one-call helper that
  installs the full kit middleware stack in the recommended order.

Order matters because Starlette wraps in *reverse* of the
``add_middleware`` call sequence: the **last** middleware added is the
**outermost**. Adopters who want a custom order should bypass
:func:`install_middleware_stack` and call ``app.add_middleware`` directly.

Recommended outer→inner stack (matches LLD §11 — exceptions and
security headers must observe everything):

1. :class:`ExceptionLoggingMiddleware` — catches every uncaught raise.
2. :class:`SecurityHeadersMiddleware` — runs on the response after the
   inner stack finishes so kit-generated 4xx / 5xx envelopes still get
   the hardening headers.
3. :class:`RateLimitHeadersMiddleware` — converts
   :class:`RateLimitError` into 429 + the canonical ``X-RateLimit-*``
   headers. Runs *inside* exception handling so the raise still
   propagates.
4. :class:`SelectiveCorsMiddleware` — CORS only on configured prefixes.
5. :class:`BodyLimitMiddleware` — short-circuits oversize requests
   before they reach the route.
6. :class:`RequestIdMiddleware` — seeds the request-id ContextVar; must
   be innermost so every other middleware reads it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resilience_kit.exceptions import MissingExtraError
from resilience_kit.middleware import (
    BodyLimitMiddleware,
    ExceptionLoggingMiddleware,
    RateLimitHeadersMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    SelectiveCorsMiddleware,
)

try:
    import fastapi  # noqa: F401  extra-gate guard.
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("fastapi", "prajwal-resilience-kit[fastapi]") from exc

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from fastapi import FastAPI


def install_middleware_stack(
    app: FastAPI,
    *,
    body_limit_bytes: int = 1_048_576,
    request_id_header: str = "x-request-id",
    correlation_id_header: str = "x-correlation-id",
    security_header_overrides: Mapping[str, str] | None = None,
    security_header_extras: Mapping[str, str] | None = None,
    cors_allow_origins: Sequence[str] | None = None,
    cors_path_prefixes: Sequence[str] | None = None,
) -> None:
    """Install the recommended kit middleware stack on ``app``.

    The function follows Starlette's "last call wins outermost"
    semantics, so the call order is innermost → outermost (the source
    reads top-to-bottom from inside the stack out).

    Args:
        app: Target FastAPI application.
        body_limit_bytes: Max ``Content-Length`` accepted before 413.
        request_id_header: Inbound / outbound request-id header name.
        correlation_id_header: Inbound / outbound correlation-id header name.
        security_header_overrides: Replacement values for the default
            security headers — see
            :data:`~resilience_kit.middleware.SECURITY_HEADER_DEFAULTS`.
        security_header_extras: Additional headers to merge alongside
            the defaults.
        cors_allow_origins: If both this and ``cors_path_prefixes`` are
            non-empty, install :class:`SelectiveCorsMiddleware`. Skip
            the layer otherwise so apps that handle CORS upstream are
            not double-wrapped.
        cors_path_prefixes: Path prefixes to apply CORS to (e.g.
            ``["/api"]``).
    """
    # Innermost first.
    app.add_middleware(
        RequestIdMiddleware,
        header=request_id_header,
        correlation_header=correlation_id_header,
    )
    app.add_middleware(BodyLimitMiddleware, max_bytes=body_limit_bytes)
    if cors_allow_origins and cors_path_prefixes:
        app.add_middleware(
            SelectiveCorsMiddleware,
            allow_origins=cors_allow_origins,
            path_prefixes=cors_path_prefixes,
        )
    app.add_middleware(RateLimitHeadersMiddleware)
    app.add_middleware(
        SecurityHeadersMiddleware,
        overrides=security_header_overrides,
        extra=security_header_extras,
    )
    app.add_middleware(ExceptionLoggingMiddleware)


__all__ = [
    "BodyLimitMiddleware",
    "ExceptionLoggingMiddleware",
    "RateLimitHeadersMiddleware",
    "RequestIdMiddleware",
    "SecurityHeadersMiddleware",
    "SelectiveCorsMiddleware",
    "install_middleware_stack",
]
