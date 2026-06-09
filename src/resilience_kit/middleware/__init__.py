"""Framework-agnostic ASGI middleware (ROADMAP M4).

Every middleware is an :class:`ASGI3 <typing.Protocol>`-shaped callable
that wraps an inner ``app``. The FastAPI adapter (M5) and Django ASGI
adapter (M6) consume these directly; classic-Django WSGI uses the WSGI
mirrors land in M6 alongside the adapter.
"""

from __future__ import annotations

from resilience_kit.middleware.request_id import RequestIdMiddleware

__all__ = ["RequestIdMiddleware"]
