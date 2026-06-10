"""FastAPI adapter (ROADMAP M5).

Wires the kit into FastAPI's lifespan, dependency-injection,
middleware, and exception-handler hooks. Re-exports the public surfaces
that adopters consume; internal helpers stay private.
"""

from __future__ import annotations

from resilience_kit.adapters.fastapi.dependencies import rate_limit, request_id_dep
from resilience_kit.adapters.fastapi.exception_handlers import install as install_exception_handlers
from resilience_kit.adapters.fastapi.lifespan import (
    install_health_routes,
    resilience_lifespan,
)
from resilience_kit.adapters.fastapi.middleware import install_middleware_stack

__all__ = [
    "install_exception_handlers",
    "install_health_routes",
    "install_middleware_stack",
    "rate_limit",
    "request_id_dep",
    "resilience_lifespan",
]
