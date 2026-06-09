"""Mini-package proving the kit's entry-point resolution chain.

Installed by the contract test via ``uv pip install -e
tests/fixtures/fake_third_party`` so the standard provider chain
(:func:`resilience_kit._providers.resolve_provider`) can discover its
exports under ``resilience_kit.cache_backends`` /
``resilience_kit.audit_backends``.
"""

from __future__ import annotations
