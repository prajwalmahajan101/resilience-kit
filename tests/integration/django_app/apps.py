"""Django AppConfig for the M6 integration test app."""

from __future__ import annotations

from django.apps import AppConfig


class DjangoAppConfig(AppConfig):  # type: ignore[misc]
    """Test-only AppConfig — declares the label models reference."""

    name = "tests.integration.django_app"
    label = "django_app"
