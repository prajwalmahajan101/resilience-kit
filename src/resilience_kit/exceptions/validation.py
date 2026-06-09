"""Validation- and rate-limit-tier exceptions.

Adapters map :class:`ValidationError` → HTTP 400 and :class:`RateLimitError`
→ HTTP 429 (with a ``Retry-After`` header from
:meth:`RateLimitError.response_headers`). See LLD §11.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.exceptions.base import ResilienceKitError

if TYPE_CHECKING:
    from collections.abc import Mapping


class ValidationError(ResilienceKitError):
    """A value did not pass a validation rule.

    Examples: SSRF guard rejected a URL, ``Rate.parse`` got bad input,
    a setting required at startup is missing.
    """

    error_code = "VALIDATION_ERROR"


class RateLimitError(ResilienceKitError):
    """A throttle gate denied the call.

    Carries the request-shaped fields adapters need to build the standard
    rate-limit response (``Retry-After`` and ``X-RateLimit-*`` headers).
    """

    error_code = "RATE_LIMIT_EXCEEDED"

    def __init__(
        self,
        *,
        limit: int,
        remaining: int,
        reset_at: int,
        retry_after: float,
        scope: str | None = None,
        message: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialise with throttle-decision fields.

        Args:
            limit: The limit that was hit (e.g. ``60``).
            remaining: Tokens left in the window — typically ``0``.
            reset_at: Unix-seconds timestamp when the window resets.
            retry_after: Seconds the caller should wait before retrying.
            scope: Optional scope label (``"ip"``, ``"endpoint"``, …).
            message: Optional human-readable override.
            details: Optional extra payload (merged with the above).
        """
        merged: dict[str, Any] = {
            "limit": limit,
            "remaining": remaining,
            "reset_at": reset_at,
            "retry_after": retry_after,
        }
        if scope is not None:
            merged["scope"] = scope
        if details:
            merged.update(details)
        super().__init__(
            message or f"Rate limit exceeded (limit={limit}, retry_after={retry_after:.2f}s).",
            details=merged,
        )
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
        self.retry_after = retry_after
        self.scope = scope

    def response_headers(self) -> dict[str, str]:
        """Return the standard rate-limit headers for a 429 response.

        Returns:
            A dict suitable for direct splatting into a Starlette / DRF
            response: ``Retry-After`` + the conventional ``X-RateLimit-*``
            triple.
        """
        return {
            "Retry-After": str(max(1, int(self.retry_after) + (self.retry_after % 1 > 0))),
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_at),
        }
