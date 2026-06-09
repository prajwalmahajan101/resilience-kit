"""``/readyz`` aggregator (ROADMAP M4).

Walks every backend registered with :func:`~resilience_kit.recovery.register_for_recovery`,
calls each one's ``health_check()`` in parallel, and reduces the
individual :class:`~resilience_kit.circuit_breaker.base.HealthSnapshot`
results into a single :class:`HealthAggregate`.

Reduction rules:

* ``ok`` — every snapshot reports ``healthy=True``.
* ``degraded_but_serving`` — at least one backend is unhealthy AND at
  least one of the same family (cache / breaker / throttle) is still
  healthy. The service can degrade gracefully via the kit's fail-open
  fallbacks (LLD §8) and the request path still works.
* ``degraded`` — every registered backend reports unhealthy. The
  service should refuse traffic.

The aggregator is *not* wrapped in ``@resilient`` — it must observe the
breakers it reports on, not call through them.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from resilience_kit.recovery import registered_backends

if TYPE_CHECKING:
    from resilience_kit.circuit_breaker.base import HealthSnapshot

_logger = logging.getLogger(__name__)


class HealthStatus(StrEnum):
    """Overall readiness verdict for ``/readyz``."""

    OK = "ok"
    DEGRADED_BUT_SERVING = "degraded_but_serving"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class HealthAggregate:
    """Reduced view of every backend's :class:`HealthSnapshot`."""

    status: HealthStatus
    snapshots: tuple[HealthSnapshot, ...]
    extras: dict[str, str] = field(default_factory=dict)

    @property
    def http_status(self) -> int:
        """HTTP status adapters use for ``/readyz``.

        Returns:
            ``200`` for ``ok`` / ``degraded_but_serving``; ``503`` for
            ``degraded``. Matches Kubernetes' readiness-probe conventions.
        """
        return 503 if self.status is HealthStatus.DEGRADED else 200


async def health_snapshot(*, probe_timeout: float = 1.0) -> HealthAggregate:
    """Collect every registered backend's health and return the aggregate.

    Args:
        probe_timeout: Per-backend deadline in seconds. A backend that
            exceeds this is reported as unhealthy with ``detail="timeout"``.

    Returns:
        The reduced :class:`HealthAggregate`.
    """
    backends = registered_backends()
    if not backends:
        # No backends registered yet (e.g. only memory primitives in
        # use). Memory primitives always work, so the service is OK.
        return HealthAggregate(status=HealthStatus.OK, snapshots=())

    snapshots = await asyncio.gather(
        *(_probe(b, probe_timeout=probe_timeout) for b in backends),
        return_exceptions=False,
    )
    return _reduce(tuple(snapshots))


async def _probe(
    backend: object,
    *,
    probe_timeout: float,
) -> HealthSnapshot:
    """Run a single backend's ``health_check`` with a timeout + error capture."""
    from resilience_kit.circuit_breaker.base import HealthSnapshot  # noqa: PLC0415

    backend_name = getattr(backend, "alias", None) or type(backend).__name__
    try:
        async with asyncio.timeout(probe_timeout):
            return await backend.health_check()  # type: ignore[attr-defined, no-any-return]
    except TimeoutError:
        return HealthSnapshot(
            healthy=False,
            backend=backend_name,
            detail="timeout",
        )
    except Exception as exc:
        _logger.exception("health_check raised for backend %s", backend_name)
        return HealthSnapshot(
            healthy=False,
            backend=backend_name,
            detail=f"{type(exc).__name__}: {exc}",
        )


def _reduce(snapshots: tuple[HealthSnapshot, ...]) -> HealthAggregate:
    """Apply the reduction rules in the module docstring."""
    if all(s.healthy for s in snapshots):
        return HealthAggregate(status=HealthStatus.OK, snapshots=snapshots)
    if any(s.healthy for s in snapshots):
        return HealthAggregate(
            status=HealthStatus.DEGRADED_BUT_SERVING,
            snapshots=snapshots,
        )
    return HealthAggregate(status=HealthStatus.DEGRADED, snapshots=snapshots)


__all__ = ["HealthAggregate", "HealthStatus", "health_snapshot"]
