"""Views + URL conf for the M6 integration app."""

from __future__ import annotations

from typing import Any

from django.http import JsonResponse
from django.urls import path
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.request import Request  # noqa: TC002 — runtime use by DRF decorators.
from rest_framework.response import Response

from resilience_kit.adapters.django.drf_throttles import IPThrottle
from tests.integration.django_app.models import Secret


class _IPThrottle2PerMin(IPThrottle):
    rate = "2/min"


def hi(_request: Any) -> JsonResponse:
    return JsonResponse({"h": "i"})


@api_view(["GET"])
@throttle_classes([_IPThrottle2PerMin])
def limited(_request: Request) -> Response:
    return Response({"ok": "yes"})


@api_view(["POST", "GET"])
def secrets(request: Request) -> Response:
    if request.method == "POST":
        s = Secret.objects.create(value=request.data["value"])
        return Response({"id": s.pk})
    return Response({"items": list(Secret.objects.values("id", "value"))})


urlpatterns = [
    path("hi", hi),
    path("limited", limited),
    path("secrets", secrets),
]
