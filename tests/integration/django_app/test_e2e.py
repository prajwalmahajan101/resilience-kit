"""End-to-end test for the Django adapter (ROADMAP M6 exit gate)."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


def test_middleware_request_id_and_security_headers(django_app: None) -> None:
    """Hi route echoes the request id and carries the security header."""
    from django.test import Client  # noqa: PLC0415

    response = Client().get("/hi")
    assert response.status_code == 200
    assert response.headers["X-Request-Id"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_ip_throttle_denies_third_request(django_app: None) -> None:
    """The 3rd /limited request returns 429 with X-RateLimit-* headers."""
    from django.test import Client  # noqa: PLC0415

    from resilience_kit.testing import reset_all_singletons  # noqa: PLC0415

    reset_all_singletons()
    c = Client()
    assert c.get("/limited").status_code == 200
    assert c.get("/limited").status_code == 200
    response = c.get("/limited")
    assert response.status_code == 429
    body = response.json()
    assert body["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert response.headers["Retry-After"]
    assert response.headers["X-RateLimit-Limit"] == "2"


def test_encrypted_charfield_round_trips_through_postgres(django_app: None) -> None:
    """Cipher on disk; plaintext through the ORM."""
    from django.db import connection  # noqa: PLC0415
    from django.test import Client  # noqa: PLC0415

    c = Client()
    create = c.post(
        "/secrets",
        data='{"value": "top secret"}',
        content_type="application/json",
    )
    assert create.status_code == 200
    secret_id = create.json()["id"]

    read = c.get("/secrets")
    assert read.status_code == 200
    items = read.json()["items"]
    assert any(i["id"] == secret_id and i["value"] == "top secret" for i in items)

    with connection.cursor() as cur:
        cur.execute("SELECT value FROM django_app_secret WHERE id = %s", [secret_id])
        on_disk = cur.fetchone()[0]
    assert on_disk != "top secret"
    assert on_disk.startswith("gAAAAA")


def test_management_commands_run(django_app: None) -> None:
    """resilience_status renders; resilience_reset requires a target."""
    import io  # noqa: PLC0415

    from django.core.management import CommandError, call_command  # noqa: PLC0415

    out = io.StringIO()
    call_command("resilience_status", stdout=out)
    text = out.getvalue()
    assert "Overall status:" in text

    # resilience_reset without a target should fail loudly.
    with pytest.raises(CommandError):
        call_command("resilience_reset")
