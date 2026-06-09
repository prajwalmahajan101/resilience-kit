"""SSRF guard — outbound URL validation + allow-list (LLD §5).

Public surface lands in M3 commit 2 (``guard.py``); this commit ships the
IP-classification primitives only.
"""

from __future__ import annotations
