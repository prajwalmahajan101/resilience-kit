"""FastAPI adapter (ROADMAP M5).

Wires the kit into FastAPI's lifespan, dependency-injection,
middleware, and exception-handler hooks. Re-exports the public surfaces
that adopters consume; internal helpers stay private.
"""

from __future__ import annotations

from resilience_kit.adapters.fastapi.lifespan import (
    install_health_routes,
    resilience_lifespan,
)

__all__ = [
    "install_health_routes",
    "resilience_lifespan",
]
