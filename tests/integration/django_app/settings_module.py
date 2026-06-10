"""Django settings module for the M6 integration suite.

Built at import time so pytest-django can point ``DJANGO_SETTINGS_MODULE``
at it without further wiring. The database is configured lazily via a
fixture-injected DSN — see ``conftest.py``.
"""

from __future__ import annotations

import os

SECRET_KEY = "test-secret-key" + "x" * 50
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "resilience_kit.adapters.django",
    "tests.integration.django_app.apps.DjangoAppConfig",
]

MIDDLEWARE = [
    "resilience_kit.adapters.django.middleware.ExceptionLoggingMiddleware",
    "resilience_kit.adapters.django.middleware.SecurityHeadersMiddleware",
    "resilience_kit.adapters.django.middleware.RateLimitHeadersMiddleware",
    "resilience_kit.adapters.django.middleware.RequestIdMiddleware",
]

ROOT_URLCONF = "tests.integration.django_app.views"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        # Fields filled at fixture time by conftest.py.
        "HOST": os.environ.get("M6_PG_HOST", "localhost"),
        "PORT": os.environ.get("M6_PG_PORT", "5432"),
        "NAME": os.environ.get("M6_PG_DB", "test"),
        "USER": os.environ.get("M6_PG_USER", "test"),
        "PASSWORD": os.environ.get("M6_PG_PASSWORD", "test"),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "resilience_kit.adapters.django.exception_handler.handle",
}
