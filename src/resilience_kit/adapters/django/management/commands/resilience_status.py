"""``manage.py resilience_status`` — print per-service and per-backend health."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from resilience_kit.exceptions import MissingExtraError
from resilience_kit.health import health_snapshot
from resilience_kit.registry import registry

try:
    from django.core.management.base import BaseCommand
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("django", "prajwal-resilience-kit[django]") from exc


class Command(BaseCommand):  # type: ignore[misc]
    """Dump the kit's health + per-service breaker state to stdout."""

    help = "Print resilience-kit health (per-backend) and breaker state."

    def add_arguments(self, parser: Any) -> None:
        """Accept ``--json`` for machine-readable output."""
        parser.add_argument("--json", action="store_true", help="emit JSON instead of text")

    def handle(self, *_args: Any, **options: Any) -> None:
        """Collect aggregate + per-service breaker state and print."""
        aggregate = asyncio.run(health_snapshot())
        service_states = asyncio.run(registry.health_snapshot())
        payload: dict[str, Any] = {
            "status": aggregate.status.value,
            "http_status": aggregate.http_status,
            "backends": [
                {
                    "backend": s.backend,
                    "healthy": s.healthy,
                    "detail": s.detail,
                }
                for s in aggregate.snapshots
            ],
            "services": {
                name: {"backend": snap.backend, "healthy": snap.healthy, "detail": snap.detail}
                for name, snap in service_states.items()
            },
        }
        if options.get("json"):
            self.stdout.write(json.dumps(payload, indent=2))
            return
        self.stdout.write(f"Overall status: {payload['status']} (HTTP {payload['http_status']})")
        self.stdout.write("\nBackends:")
        for row in payload["backends"]:
            mark = "OK" if row["healthy"] else "DEGRADED"
            detail = f" — {row['detail']}" if row["detail"] else ""
            self.stdout.write(f"  [{mark}] {row['backend']}{detail}")
        self.stdout.write("\nServices:")
        if not payload["services"]:
            self.stdout.write("  (none registered)")
        for name, snap in payload["services"].items():
            mark = "OK" if snap["healthy"] else "DEGRADED"
            self.stdout.write(f"  [{mark}] {name} ({snap['backend']})")


__all__ = ["Command"]
