"""Django middleware classes mirroring the kit's six ASGI middleware.

The kit's ASGI classes (under ``resilience_kit.middleware``) consume
``scope / receive / send`` — incompatible with Django's
``get_response(request) -> response`` contract. Each class here
re-implements the *semantics* of one kit ASGI middleware against
Django's request / response objects. Both sync and async modes are
supported via ``sync_capable`` + ``async_capable``; Django picks the
right path at install time based on whether the project uses WSGI or
ASGI.

Why duplicate rather than wrap: the adapters never own business
logic, but they DO own the framework's request shape. Wrapping the
ASGI class would require building synthetic scope / send callables
inside every Django request, which is more glue and more places to
miss an edge case.

Recommended `MIDDLEWARE` order (outermost first — Django runs the
list top→down on the request path, bottom→up on the response path):

.. code-block:: python

    MIDDLEWARE = [
        "resilience_kit.adapters.django.middleware.ExceptionLoggingMiddleware",
        "resilience_kit.adapters.django.middleware.SecurityHeadersMiddleware",
        "resilience_kit.adapters.django.middleware.RateLimitHeadersMiddleware",
        "resilience_kit.adapters.django.middleware.SelectiveCorsMiddleware",
        "resilience_kit.adapters.django.middleware.BodyLimitMiddleware",
        "resilience_kit.adapters.django.middleware.RequestIdMiddleware",
        ...,
    ]
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from resilience_kit.context import (
    correlation_id as correlation_id_var,
    new_request_id,
    request_id as request_id_var,
)
from resilience_kit.exceptions import (
    MissingExtraError,
    RateLimitError,
    ResilienceKitError,
    ValidationError,
    http_status_for,
)
from resilience_kit.middleware.security_headers import DEFAULTS as SECURITY_HEADER_DEFAULTS

try:
    from django.http import HttpResponse, JsonResponse
except ImportError as exc:  # pragma: no cover
    raise MissingExtraError("django", "prajwal-resilience-kit[django]") from exc

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from django.http import HttpRequest

    GetResponse = Callable[[HttpRequest], HttpResponse | Awaitable[HttpResponse]]

_logger = logging.getLogger("resilience_kit.adapters.django.middleware")


class RequestIdMiddleware:
    """Seed the ``request_id`` / ``correlation_id`` ContextVars and echo them.

    Reads the incoming ``X-Request-Id`` / ``X-Correlation-Id`` headers
    (overridable via the ``RESILIENCE_REQUEST_ID_HEADER`` /
    ``RESILIENCE_CORRELATION_ID_HEADER`` Django settings). Generates a
    fresh request id when none is supplied so downstream audit + logs
    always have a value.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        """Wrap ``get_response``."""
        self.get_response = get_response
        from django.conf import settings as django_settings  # noqa: PLC0415

        self._req_header = getattr(django_settings, "RESILIENCE_REQUEST_ID_HEADER", "X-Request-Id")
        self._corr_header = getattr(
            django_settings,
            "RESILIENCE_CORRELATION_ID_HEADER",
            "X-Correlation-Id",
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Sync path."""
        token_req, token_corr, ids = self._enter(request)
        try:
            response = self.get_response(request)
            self._tag_response(response, ids)
            return response
        finally:
            request_id_var.reset(token_req)
            correlation_id_var.reset(token_corr)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Async path — same shape as ``__call__`` but awaits the inner."""
        token_req, token_corr, ids = self._enter(request)
        try:
            response = await self.get_response(request)
            self._tag_response(response, ids)
            return response
        finally:
            request_id_var.reset(token_req)
            correlation_id_var.reset(token_corr)

    def _enter(self, request: HttpRequest) -> tuple[Any, Any, tuple[str, str]]:
        incoming_req = request.headers.get(self._req_header) or new_request_id()
        incoming_corr = request.headers.get(self._corr_header) or incoming_req
        token_req = request_id_var.set(incoming_req)
        token_corr = correlation_id_var.set(incoming_corr)
        return token_req, token_corr, (incoming_req, incoming_corr)

    def _tag_response(self, response: HttpResponse, ids: tuple[str, str]) -> None:
        req_id, corr_id = ids
        response.headers[self._req_header] = req_id
        response.headers[self._corr_header] = corr_id


class BodyLimitMiddleware:
    """Reject requests whose ``Content-Length`` exceeds the configured cap."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        """Wrap ``get_response``."""
        from django.conf import settings as django_settings  # noqa: PLC0415

        self.get_response = get_response
        self._max_bytes = int(
            getattr(django_settings, "RESILIENCE_BODY_LIMIT_BYTES", 1_048_576),
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Sync path."""
        if self._exceeds(request):
            return HttpResponse(status=413)
        return self.get_response(request)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Async path."""
        if self._exceeds(request):
            return HttpResponse(status=413)
        return await self.get_response(request)

    def _exceeds(self, request: HttpRequest) -> bool:
        length = request.headers.get("Content-Length")
        if length is None:
            return False
        try:
            return int(length) > self._max_bytes
        except ValueError:
            return False


class SecurityHeadersMiddleware:
    """Attach baseline security headers to every response."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        """Wrap ``get_response`` and merge overrides from Django settings."""
        from django.conf import settings as django_settings  # noqa: PLC0415

        self.get_response = get_response
        merged: dict[str, str] = dict(SECURITY_HEADER_DEFAULTS)
        overrides = getattr(django_settings, "RESILIENCE_SECURITY_HEADER_OVERRIDES", {})
        extras = getattr(django_settings, "RESILIENCE_SECURITY_HEADER_EXTRAS", {})
        merged.update(overrides)
        merged.update(extras)
        self._headers = merged

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Sync path."""
        response = self.get_response(request)
        self._apply(response)
        return response

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Async path."""
        response = await self.get_response(request)
        self._apply(response)
        return response

    def _apply(self, response: HttpResponse) -> None:
        for name, value in self._headers.items():
            response.headers.setdefault(name, value)


class SelectiveCorsMiddleware:
    """CORS — only on path prefixes the project opts in to."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        """Wrap ``get_response`` and read CORS knobs from Django settings."""
        from django.conf import settings as django_settings  # noqa: PLC0415

        self.get_response = get_response
        self._allow_origins = list(
            getattr(django_settings, "RESILIENCE_CORS_ALLOW_ORIGINS", []),
        )
        self._prefixes = tuple(
            getattr(django_settings, "RESILIENCE_CORS_PATH_PREFIXES", []),
        )
        self._allow_methods = ",".join(
            getattr(
                django_settings,
                "RESILIENCE_CORS_ALLOW_METHODS",
                ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
            ),
        )
        self._allow_headers = ",".join(
            getattr(
                django_settings,
                "RESILIENCE_CORS_ALLOW_HEADERS",
                ("Content-Type", "Authorization", "X-Request-Id"),
            ),
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Sync path."""
        response = self.get_response(request)
        if self._opted_in(request):
            self._apply(request, response)
        return response

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Async path."""
        response = await self.get_response(request)
        if self._opted_in(request):
            self._apply(request, response)
        return response

    def _opted_in(self, request: HttpRequest) -> bool:
        if not self._prefixes or not self._allow_origins:
            return False
        return any(request.path.startswith(p) for p in self._prefixes)

    def _apply(self, request: HttpRequest, response: HttpResponse) -> None:
        origin = request.headers.get("Origin")
        if origin and ("*" in self._allow_origins or origin in self._allow_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = self._allow_methods
        response.headers["Access-Control-Allow-Headers"] = self._allow_headers


class RateLimitHeadersMiddleware:
    """Convert :class:`RateLimitError` into a 429 with the canonical headers.

    Implements both ``__call__`` (catches raises *outside* the view, e.g.
    from inner middleware) and ``process_exception`` (Django's hook for
    view-raised exceptions). Same target — different entry points.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        """Wrap ``get_response``."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Sync path."""
        try:
            return self.get_response(request)
        except RateLimitError as exc:
            return _rate_limit_response(exc)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Async path."""
        try:
            return await self.get_response(request)
        except RateLimitError as exc:
            return _rate_limit_response(exc)

    def process_exception(
        self,
        request: HttpRequest,
        exception: BaseException,
    ) -> HttpResponse | None:
        """Map view-raised :class:`RateLimitError` to a 429 response."""
        if isinstance(exception, RateLimitError):
            return _rate_limit_response(exception)
        return None


class ExceptionLoggingMiddleware:
    """Map every uncaught :class:`ResilienceKitError` to the LLD §11 envelope.

    Implements ``process_exception`` (Django's hook for view-raised
    exceptions) as well as ``__call__`` so kit errors raised from inner
    middleware are also caught.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        """Wrap ``get_response``."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Sync path."""
        try:
            return self.get_response(request)
        except ResilienceKitError as exc:
            return _kit_error_response(exc)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Async path."""
        try:
            return await self.get_response(request)
        except ResilienceKitError as exc:
            return _kit_error_response(exc)

    def process_exception(
        self,
        request: HttpRequest,
        exception: BaseException,
    ) -> HttpResponse | None:
        """Map view-raised :class:`ResilienceKitError` to the LLD §11 envelope."""
        if isinstance(exception, ResilienceKitError):
            return _kit_error_response(exception)
        return None


def _rate_limit_response(exc: RateLimitError) -> HttpResponse:
    response = JsonResponse(
        {
            "error_code": exc.error_code,
            "message": str(exc),
            "details": dict(exc.details),
        },
        status=429,
    )
    for name, value in exc.response_headers().items():
        response.headers[name] = value
    return response


def _kit_error_response(exc: ResilienceKitError) -> HttpResponse:
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
            "request_id": request_id_var.get(),
        },
    )
    body = json.dumps(
        {
            "error_code": exc.error_code,
            "message": str(exc),
            "details": dict(exc.details),
        },
    )
    if isinstance(exc, RateLimitError):
        response = HttpResponse(body, status=status, content_type="application/json")
        for name, value in exc.response_headers().items():
            response.headers[name] = value
        return response
    return HttpResponse(body, status=status, content_type="application/json")


__all__ = [
    "BodyLimitMiddleware",
    "ExceptionLoggingMiddleware",
    "RateLimitHeadersMiddleware",
    "RequestIdMiddleware",
    "SecurityHeadersMiddleware",
    "SelectiveCorsMiddleware",
]
