"""Django adapter (ROADMAP M6).

Wires the kit into Django's `AppConfig.ready()` lifecycle, middleware
chain, DRF throttle classes, DRF exception handler, model fields, and
management commands. Pure glue; no business logic.

Django is sync-first; the kit is async-first. The bridge lives in
``apps.py``: a daemon thread owns a private asyncio loop and drives the
recovery monitor for the lifetime of the worker. ADR 0011 documents
the bridge in full.

This module exposes the AppConfig path Django expects:

.. code-block:: python

    # settings.py
    INSTALLED_APPS = [
        ...,
        "resilience_kit.adapters.django",
    ]
"""

from __future__ import annotations

default_app_config = "resilience_kit.adapters.django.apps.ResilienceConfig"

__all__ = ["default_app_config"]
