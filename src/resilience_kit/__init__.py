"""``prajwal-resilience-kit`` — framework-agnostic Python resilience kernel.

Public re-exports are added per milestone as primitives land. At M0 only
``__version__`` is exposed; ``@retry``, ``@circuit_breaker``, ``@resilient``,
and the registry arrive in M1.

See ``docs/PRD.md`` and ``docs/ROADMAP.md`` for the shipping plan.
"""

from resilience_kit._version import __version__

__all__ = ["__version__"]
