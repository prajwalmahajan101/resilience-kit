"""Outbound HTTP client — SSRF + DNS-pin + breaker + retry + audit (LLD §5).

This package requires the ``http`` extra (``pip install
'prajwal-resilience-kit[http]'``). The submodules raise
:class:`~resilience_kit.exceptions.MissingExtraError` at import time when
``httpx`` is not installed, so the failure mode is immediate and the
install hint is unambiguous.

Public surface lands incrementally across M3:

* commit 3 — :mod:`.errors`
* commit 4 — :mod:`.auth`
* commit 5 — :mod:`.dns_pin`
* commit 6 — :mod:`.session`
* commit 7 — :class:`AsyncAPIClient`
"""

from __future__ import annotations
