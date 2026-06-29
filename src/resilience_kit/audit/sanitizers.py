"""Payload sanitisers for the audit subsystem.

The :class:`Sanitizer` Protocol takes one (possibly deeply nested)
payload and returns a redacted copy ready for storage. Backends are
NOT expected to do their own redaction — the kit guarantees that
events reaching :meth:`AuditBackend.write_many` are already safe.

The default :class:`DefaultRedactor` walks dicts/lists and replaces
the *value* of every key whose lower-case name matches one of the
configured redact-field substrings with ``"[REDACTED]"``. Configurable
via ``settings.audit.redact_fields``.

Field-name matching alone misses sensitive data carried *inside* an
otherwise-innocuous value — e.g. ``{"notes": "customer PAN ABCDE1234F"}``.
:class:`RegexRedactor` adds value-scanning: it scrubs substrings of
string leaves that match a configured list of :class:`PiiPattern`.
:class:`IndiaFintechRedactor` is the batteries-included variant that
layers the global + India PII packs on top of the default field set;
it ships under the ``india_fintech`` sanitiser entry point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

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
        "cookie",
        "set-cookie",
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


def _luhn_ok(candidate: str) -> bool:
    """Return ``True`` when the digits of ``candidate`` pass the Luhn check.

    Used to keep the credit-card pattern from masking arbitrary 13-to-19
    digit runs (order numbers, timestamps) that happen to be the right
    length. Non-digit characters (spaces, dashes) are ignored.
    """
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        doubled = digit * 2 if index % 2 == parity else digit
        checksum += doubled - 9 if doubled > 9 else doubled
    return checksum % 10 == 0


@dataclass(frozen=True)
class PiiPattern:
    """A named value-scanning rule.

    Attributes:
        name: Human-readable rule id (e.g. ``"pan"``) for documentation.
        pattern: Compiled regex applied to string leaves.
        validator: Optional predicate run on each match; the match is
            masked only when it returns ``True``. ``None`` masks every
            match. Used for Luhn-checked card numbers.
    """

    name: str
    pattern: re.Pattern[str]
    validator: Callable[[str], bool] | None = None


# Region-neutral patterns: credit cards (Luhn-checked), emails embedded in
# free text, and IBANs. Card matching is deliberately gated on Luhn so a bare
# 16-digit identifier is not redacted unless it is a plausible card.
GLOBAL_PII_PATTERNS: tuple[PiiPattern, ...] = (
    PiiPattern(
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    PiiPattern(
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Za-z0-9]{11,30}\b"),
    ),
    PiiPattern(
        "credit_card",
        re.compile(r"\b\d(?:[ -]?\d){12,18}\b"),
        _luhn_ok,
    ),
)

# India-specific identifiers. ``bank_account`` is intentionally broad
# (any 9-to-18 digit run): appropriate for an opt-in fintech pack where
# over-redaction in audit logs is safer than a leak.
INDIA_PII_PATTERNS: tuple[PiiPattern, ...] = (
    PiiPattern("pan", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    PiiPattern("ifsc", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    # Mobile runs before aadhaar: a ``+91``-prefixed number is 12 digits
    # and would otherwise be half-eaten by the 12-digit aadhaar rule. The
    # lookbehind/lookahead anchor the whole token (incl. the ``+91``/``0``).
    PiiPattern("mobile_in", re.compile(r"(?<!\w)(?:\+91|0)?[6-9]\d{9}(?!\d)")),
    PiiPattern("aadhaar", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    PiiPattern("bank_account", re.compile(r"\b\d{9,18}\b")),
)


class RegexRedactor(DefaultRedactor):
    """Field-name redaction plus value-scanning over string leaves.

    Inherits :class:`DefaultRedactor`'s key-name matching, then scrubs
    any string leaf that survives it against :attr:`PATTERNS` (or the
    ``patterns`` passed to the constructor). The matched substring — not
    the whole value — is replaced with :data:`REDACTED`, so
    ``"customer PAN ABCDE1234F"`` becomes ``"customer PAN [REDACTED]"``.
    """

    PATTERNS: tuple[PiiPattern, ...] = ()

    def __init__(
        self,
        fields: Iterable[str] | None = None,
        *,
        patterns: Iterable[PiiPattern] | None = None,
    ) -> None:
        """Configure the field set and the value-scanning patterns.

        Args:
            fields: Field-name substrings, as in :class:`DefaultRedactor`.
            patterns: Value-scanning rules. When ``None``, :attr:`PATTERNS`
                is used (empty for the base class).
        """
        super().__init__(fields)
        self._patterns = tuple(patterns) if patterns is not None else self.PATTERNS

    def _walk(self, value: Any) -> Any:
        walked = super()._walk(value)
        if isinstance(walked, str):
            return self._scrub(walked)
        return walked

    def _scrub(self, text: str) -> str:
        for rule in self._patterns:
            validator = rule.validator
            if validator is None:
                text = rule.pattern.sub(REDACTED, text)
            else:

                def _replace(match: re.Match[str], check: Callable[[str], bool] = validator) -> str:
                    return REDACTED if check(match.group()) else match.group()

                text = rule.pattern.sub(_replace, text)
        return text


class IndiaFintechRedactor(RegexRedactor):
    """Default fields + global PII + India PII, ready to wire by name.

    Registered as the ``india_fintech`` sanitiser entry point; select it
    via ``RESILIENCE_AUDIT__SANITIZER=india_fintech``.
    """

    PATTERNS: tuple[PiiPattern, ...] = (*GLOBAL_PII_PATTERNS, *INDIA_PII_PATTERNS)


__all__ = [
    "GLOBAL_PII_PATTERNS",
    "INDIA_PII_PATTERNS",
    "REDACTED",
    "DefaultRedactor",
    "IndiaFintechRedactor",
    "PiiPattern",
    "RegexRedactor",
    "Sanitizer",
]
