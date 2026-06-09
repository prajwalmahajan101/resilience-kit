"""Audit (``api_log``) subsystem (ROADMAP M4).

Decorators (:func:`log_inbound`, :func:`log_outbound`), dispatcher
(:class:`FireAndForgetDispatcher` / :class:`InlineDispatcher`),
sanitizer (:class:`DefaultRedactor`), and pluggable backends
(``noop`` / ``stdlib_logging`` / ``postgres``).

Public surface lands incrementally across M4 commits 4-8.
"""

from __future__ import annotations

from resilience_kit.audit.backends.base import AuditBackend, AuditEvent
from resilience_kit.audit.decorators import log_inbound, log_outbound
from resilience_kit.audit.factory import (
    get_dispatcher,
    reset_dispatcher,
    set_dispatcher,
)

__all__ = [
    "AuditBackend",
    "AuditEvent",
    "get_dispatcher",
    "log_inbound",
    "log_outbound",
    "reset_dispatcher",
    "set_dispatcher",
]
