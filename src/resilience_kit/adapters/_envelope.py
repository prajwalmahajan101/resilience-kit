"""Framework-agnostic envelope builder for kit exceptions.

Both the FastAPI and Django adapters need to translate a
:class:`~resilience_kit.exceptions.ResilienceKitError` into

* a JSON-serialisable body dict,
* an HTTP status code,
* a header dict (with ``Retry-After`` + ``X-RateLimit-*`` for rate-limit errors).

Before this module they each built that triple inline, producing duplicated
code (FastAPI :func:`_envelope` and Django :func:`_build_response` had the same
body, severity, and header logic). The duplication is consolidated here so a
third adapter (Litestar / Flask / Starlette-only) gets the behaviour for free
and consumers can call :func:`from_exception` directly to wrap kit exceptions
into a non-kit envelope shape — the M7 FastAPI dogfooding fix for the
two-handler envelope collision (MIGRATION §10.2 "Option 3").

The default envelope shape (``envelope_cls=None``) is **byte-for-byte
identical** to what both adapters emitted before the refactor — LLD §11's
``{error_code, message, details}``. The ``envelope_cls`` projection is opt-in
and only consulted when a consumer hands in their own pydantic model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from resilience_kit.context import request_id
from resilience_kit.exceptions import RateLimitError, ResilienceKitError, http_status_for

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import BaseModel

# Field-name aliases recognised when projecting onto a consumer envelope model.
# Order matters — the first match wins. If a target model declares more than
# one, only the first is filled.
_ERROR_CODE_ALIASES = ("error_code", "code", "error")
_MESSAGE_ALIASES = ("message", "detail")
_DETAILS_ALIASES = ("details", "errors")


def from_exception(
    exc: ResilienceKitError,
    *,
    envelope_cls: type[BaseModel] | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], int, dict[str, str]]:
    """Build ``(body, status, headers)`` for a kit exception.

    Args:
        exc: Any :class:`ResilienceKitError` subclass instance.
        envelope_cls: Optional pydantic model whose field names should
            receive the projected values. When omitted the body is the
            locked LLD §11 shape — ``{error_code, message, details}``.
            When given, the projection looks at ``envelope_cls.model_fields``
            and writes ``error_code`` onto whichever of ``error_code | code
            | error`` is declared, ``message`` onto ``message | detail``,
            and ``details`` onto ``details`` (as a dict) or ``errors`` (as
            a list of ``{field, message}`` objects, mirroring DRF-style
            validation envelopes). A ``request_id`` field is filled from
            the current :data:`resilience_kit.context.request_id` value
            when present. A ``success`` field is set to ``False``.
            Other declared fields are left unfilled — the consumer's model
            defaults / required-field rules decide what happens.
        extra_headers: Headers the caller wants merged into the response
            (e.g. CORS, instrumentation). ``Retry-After`` + ``X-RateLimit-*``
            from :meth:`RateLimitError.response_headers` are always added
            on top for :class:`RateLimitError`.

    Returns:
        ``(body, status, headers)`` — the body is a plain dict ready to
        feed to ``JSONResponse`` / DRF ``Response`` / the consumer's
        envelope constructor. ``status`` comes from
        :func:`http_status_for`. ``headers`` is a fresh dict (never the
        caller's original).
    """
    body: dict[str, Any] = {
        "error_code": exc.error_code,
        "message": str(exc),
        "details": dict(exc.details),
    }
    status = http_status_for(exc)
    headers = dict(extra_headers or {})
    if isinstance(exc, RateLimitError):
        headers.update(exc.response_headers())
    if envelope_cls is not None:
        body = _project_onto_envelope(body, envelope_cls)
    return body, status, headers


def _project_onto_envelope(
    body: dict[str, Any],
    envelope_cls: type[BaseModel],
) -> dict[str, Any]:
    """Project the canonical body onto whatever field names ``envelope_cls`` declares."""
    fields = set(envelope_cls.model_fields)
    out: dict[str, Any] = {}

    code_field = _first_match(_ERROR_CODE_ALIASES, fields)
    if code_field is not None:
        out[code_field] = body["error_code"]

    message_field = _first_match(_MESSAGE_ALIASES, fields)
    if message_field is not None:
        out[message_field] = body["message"]

    if "details" in fields:
        out["details"] = body["details"]
    elif "errors" in fields:
        out["errors"] = _details_to_error_list(body["details"])

    if "request_id" in fields:
        out["request_id"] = request_id.get()

    if "success" in fields:
        out["success"] = False

    return out


def _first_match(candidates: tuple[str, ...], fields: set[str]) -> str | None:
    for c in candidates:
        if c in fields:
            return c
    return None


def _details_to_error_list(details: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Convert a flat ``details`` dict to the ``[{field, message}, ...]`` shape."""
    return [{"field": k, "message": str(v)} for k, v in details.items()]


__all__ = ["from_exception"]
