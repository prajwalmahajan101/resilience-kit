"""Audit (``api_log``) subsystem (ROADMAP M4).

Decorators (:func:`log_inbound`, :func:`log_outbound`), dispatcher
(:class:`FireAndForgetDispatcher` / :class:`InlineDispatcher`),
sanitizer (:class:`DefaultRedactor`), and pluggable backends
(``noop`` / ``stdlib_logging`` / ``postgres``).

Public surface lands incrementally across M4 commits 4-8.
"""

from __future__ import annotations

from resilience_kit.audit.backends.base import AuditBackend, AuditEvent

__all__ = ["AuditBackend", "AuditEvent"]
