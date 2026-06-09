"""Root exception type for ``resilience_kit``.

Every kit-raised exception carries a stable ``error_code`` and a structured
``details`` mapping. Adapters use ``error_code`` to map exceptions onto HTTP
responses (see LLD §11) without sniffing concrete classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


class ResilienceKitError(Exception):
    """Base for every exception raised by ``resilience_kit``.

    Subclasses set ``error_code`` to a stable, screaming-snake-case identifier
    used by adapters to map onto HTTP responses (LLD §11) and by observability
    pipelines as a low-cardinality label.
    """

    #: Default error code for this class. Subclasses override.
    error_code: str = "RESILIENCE_KIT_ERROR"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialise with an optional message and structured details payload.

        Args:
            message: Human-readable message; defaults to the class name.
            details: Structured payload — small, JSON-serialisable values only.
        """
        super().__init__(message or self.__class__.__name__)
        self._details: dict[str, Any] = dict(details) if details else {}

    @property
    def details(self) -> Mapping[str, Any]:
        """Return an immutable view of the structured detail payload."""
        return self._details

    def with_details(self, **extra: Any) -> ResilienceKitError:
        """Return ``self`` after merging ``extra`` into ``details``.

        Mutates in place and returns ``self`` for chaining at the raise site.

        Args:
            **extra: Additional key-value pairs to merge into ``details``.

        Returns:
            ``self`` for chaining.
        """
        self._details.update(extra)
        return self
