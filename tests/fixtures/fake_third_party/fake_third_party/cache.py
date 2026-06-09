"""Fake :class:`~resilience_kit.cache.base.AsyncCache` for the resolution test."""

from __future__ import annotations

from typing import Any


class FakeCache:
    """Trivial cache satisfying :class:`AsyncCache` at runtime.

    The contract test only asserts that the kit's provider chain finds
    this class via the ``resilience_kit.cache_backends`` entry point —
    it does NOT exercise the full cache contract.
    """

    def __init__(
        self,
        *,
        alias: str = "default",
        clock: Any = None,
    ) -> None:
        """Accept the standard kit factory kwargs."""
        self.alias = alias

    async def get(self, key: str) -> Any:
        """Return ``None`` for every key."""
        _ = key
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """Discard the value."""
        _ = (key, value, ttl)

    async def add(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Pretend nothing exists yet."""
        _ = (key, value, ttl)
        return True

    async def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        """Return ``amount`` directly."""
        _ = (key, ttl)
        return amount

    async def delete(self, key: str) -> None:
        """No-op."""
        _ = key

    async def health_check(self) -> object:
        """Return a permanently-healthy placeholder."""
        return _Healthy(alias=self.alias)


class _Healthy:
    """Permanently-healthy stand-in for :class:`HealthSnapshot`."""

    healthy = True
    detail = None
    degraded_since: float | None = None
    extra: dict[str, Any] = {}

    def __init__(self, *, alias: str) -> None:
        self.backend = f"fake({alias})"
