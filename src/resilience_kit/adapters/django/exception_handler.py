"""DRF exception handler mapping kit exceptions to the LLD §11 envelope.

DRF resolves the exception handler at request time via the
``REST_FRAMEWORK['EXCEPTION_HANDLER']`` setting. Pointing it at
:func:`handle` is enough to translate every kit exception into a
:class:`rest_framework.response.Response` with the right status,
JSON body, and (for :class:`RateLimitError`) the ``Retry-After`` +
``X-RateLimit-*`` headers.

Non-kit exceptions fall through to ``rest_framework.views.exception_handler``
so DRF's existing handlers for :class:`ValidationError`,
:class:`PermissionDenied`, etc. still apply.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from resilience_kit.context import request_id
from resilience_kit.exceptions import (
    MissingExtraError,
    RateLimitError,
    ResilienceKitError,
    ValidationError,
    http_status_for,
)

try:
    from rest_framework.response import Response
    from rest_framework.views import exception_handler as drf_default_handler
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("django", "prajwal-resilience-kit[django]") from exc

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger = logging.getLogger("resilience_kit.adapters.django.exception_handler")


def handle(exc: BaseException, context: Mapping[str, Any]) -> Response | None:
    """Map ``exc`` to a DRF ``Response`` or defer to DRF's default handler.

    Args:
        exc: The exception raised by the view / serializer / throttle.
        context: DRF's request-context dict (passed through to the
            default handler when ``exc`` is not a kit exception).

    Returns:
        A :class:`Response` for any :class:`ResilienceKitError`;
        the result of DRF's default handler otherwise (which itself
        returns ``None`` for unknown exceptions so Django's 500 path
        runs).
    """
    if isinstance(exc, ResilienceKitError):
        return _build_response(exc)
    return drf_default_handler(exc, context)


def _build_response(exc: ResilienceKitError) -> Response:
    status = http_status_for(exc)
    severity = (
        logging.WARNING if isinstance(exc, (ValidationError, RateLimitError)) else logging.ERROR
    )
    _logger.log(
        severity,
        "%s: %s",
        exc.error_code,
        exc,
        extra={
            "error_code": exc.error_code,
            "details": dict(exc.details),
            "request_id": request_id.get(),
        },
    )
    body = {
        "error_code": exc.error_code,
        "message": str(exc),
        "details": dict(exc.details),
    }
    headers = exc.response_headers() if isinstance(exc, RateLimitError) else None
    return Response(body, status=status, headers=headers)


__all__ = ["handle"]
