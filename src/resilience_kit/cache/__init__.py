"""Cache subpackage — protocol, in-memory impl, provider.

Public surface: :class:`AsyncCache`. In-memory backend ships at M1; redis
backend ships at M2.
"""

from __future__ import annotations

from resilience_kit.cache.base import AsyncCache

__all__ = ["AsyncCache"]
