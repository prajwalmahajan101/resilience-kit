"""Framework-agnostic ASGI middleware (ROADMAP M4).

Every middleware is an :class:`ASGI3 <typing.Protocol>`-shaped callable
that wraps an inner ``app``. The FastAPI adapter (M5) and Django ASGI
adapter (M6) consume these directly; classic-Django WSGI uses the WSGI
mirrors land in M6 alongside the adapter.
"""

from __future__ import annotations

from resilience_kit.middleware.body_limit import BodyLimitMiddleware
from resilience_kit.middleware.exception_logging import ExceptionLoggingMiddleware
from resilience_kit.middleware.rate_limit_headers import RateLimitHeadersMiddleware
from resilience_kit.middleware.request_id import RequestIdMiddleware
from resilience_kit.middleware.security_headers import (
    DEFAULTS as SECURITY_HEADER_DEFAULTS,
    SecurityHeadersMiddleware,
)
from resilience_kit.middleware.selective_cors import SelectiveCorsMiddleware

__all__ = [
    "SECURITY_HEADER_DEFAULTS",
    "BodyLimitMiddleware",
    "ExceptionLoggingMiddleware",
    "RateLimitHeadersMiddleware",
    "RequestIdMiddleware",
    "SecurityHeadersMiddleware",
    "SelectiveCorsMiddleware",
]
