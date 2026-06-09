"""Throttle subpackage — protocol, rate parser, scope keys.

Public surface: :class:`AsyncThrottle`, :class:`Rate`, :class:`ThrottleDecision`,
:class:`Scope`, :func:`parse_rate`, :func:`build_key`. In-memory backend ships
at M1; redis backend ships at M2.
"""

from __future__ import annotations

from resilience_kit.throttle.base import (
    AsyncThrottle,
    Rate,
    ThrottleDecision,
    parse_rate,
)
from resilience_kit.throttle.scopes import Scope, build_key

__all__ = [
    "AsyncThrottle",
    "Rate",
    "Scope",
    "ThrottleDecision",
    "build_key",
    "parse_rate",
]
