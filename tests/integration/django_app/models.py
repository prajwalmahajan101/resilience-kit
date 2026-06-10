"""Django models for the M6 integration app."""

from __future__ import annotations

from django.db import models

from resilience_kit.adapters.django.fields import EncryptedCharField


class Secret(models.Model):  # type: ignore[misc]
    """Stores plaintext in Python, Fernet ciphertext on disk."""

    value = EncryptedCharField(max_length=512)

    class Meta:
        app_label = "django_app"
