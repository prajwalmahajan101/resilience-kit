"""``manage.py resilience_reset`` — force-close a circuit breaker.

Useful when oncall is certain the upstream is healthy but the kit's
breaker is still in OPEN state. Without this command the only way to
flip a breaker is to wait for ``reset_timeout`` or restart the worker.
"""

from __future__ import annotations

import asyncio
from typing import Any

from resilience_kit.exceptions import MissingExtraError
from resilience_kit.registry import registry

try:
    from django.core.management.base import BaseCommand, CommandError
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("django", "resilience-kit[django]") from exc


class Command(BaseCommand):  # type: ignore[misc]
    """Force-close one or all registered service breakers."""

    help = "Force-close a resilience-kit breaker (single service or --all)."

    def add_arguments(self, parser: Any) -> None:
        """Accept either a service name positional or ``--all``."""
        parser.add_argument("service", nargs="?", help="service name to reset")
        parser.add_argument(
            "--all",
            action="store_true",
            dest="reset_all",
            help="reset every registered service",
        )

    def handle(self, *_args: Any, **options: Any) -> None:
        """Resolve targets and flip each to CLOSED."""
        service = options.get("service")
        reset_all = options.get("reset_all", False)
        if not service and not reset_all:
            raise CommandError("Pass a service name or --all.")
        if service and reset_all:
            raise CommandError("Pass a service name OR --all, not both.")

        if reset_all:
            targets = list(asyncio.run(registry.health_snapshot()).keys())
            if not targets:
                self.stdout.write("No services registered.")
                return
        else:
            targets = [service]  # type: ignore[list-item]

        for name in targets:
            breaker = registry.get_breaker(name)
            asyncio.run(breaker.reset())
            self.stdout.write(f"Reset breaker for {name}.")


__all__ = ["Command"]
