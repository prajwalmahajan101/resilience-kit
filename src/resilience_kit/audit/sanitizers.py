"""Payload sanitisers for the audit subsystem.

The :class:`Sanitizer` Protocol takes one (possibly deeply nested)
payload and returns a redacted copy ready for storage. Backends are
NOT expected to do their own redaction — the kit guarantees that
events reaching :meth:`AuditBackend.write_many` are already safe.

The default :class:`DefaultRedactor` walks dicts/lists and replaces
the *value* of every key whose lower-case name matches one of the
configured redact-field substrings with ``"[REDACTED]"``. Configurable
via ``settings.audit.redact_fields``; tuneable per-call by passing
``additional_fields=`` to the redactor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

REDACTED = "[REDACTED]"


@runtime_checkable
class Sanitizer(Protocol):
    """Take a payload, return a redacted copy."""

    def sanitize(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return a redacted shallow copy of ``payload``.

        Args:
            payload: Source payload — never mutated.

        Returns:
            A new dict (or nested structure) with sensitive values
            replaced by :data:`REDACTED`.
        """
        ...


class DefaultRedactor:
    """Substring-matching field-name redactor.

    A key matches the redact set when its lower-cased name *contains*
    any configured fragment — so ``"password"`` matches both
    ``"Password"`` and ``"user_password"``. Values are replaced
    in-place via a deep copy walk; nested dicts and lists are
    traversed.
    """

    DEFAULT_FIELDS: tuple[str, ...] = (
        "password",
        "token",
        "secret",
        "authorization",
        "api_key",
        "x-api-key",
    )

    def __init__(self, fields: Iterable[str] | None = None) -> None:
        """Configure with an explicit redact set.

        Args:
            fields: Iterable of substrings (case-insensitive). When
                ``None``, :data:`DEFAULT_FIELDS` is used.
        """
        chosen = tuple(fields) if fields is not None else self.DEFAULT_FIELDS
        self._fields = tuple(f.lower() for f in chosen)

    def sanitize(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return a redacted deep copy of ``payload``.

        Args:
            payload: Source mapping — never mutated.

        Returns:
            A redacted copy.
        """
        return self._walk_dict(payload)

    def _walk(self, value: Any) -> Any:
        if isinstance(value, dict):
            return self._walk_dict(value)
        if isinstance(value, list):
            return [self._walk(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self._walk(v) for v in value)
        return value

    def _walk_dict(self, source: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in source.items():
            if self._is_redacted_key(key):
                out[key] = REDACTED
            else:
                out[key] = self._walk(value)
        return out

    def _is_redacted_key(self, key: str) -> bool:
        lowered = key.lower()
        return any(fragment in lowered for fragment in self._fields)


__all__ = ["REDACTED", "DefaultRedactor", "Sanitizer"]
