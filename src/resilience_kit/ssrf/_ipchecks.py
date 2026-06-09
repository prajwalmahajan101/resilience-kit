"""IP-address classification rules used by the SSRF guard.

Pure, side-effect-free helpers over :mod:`ipaddress`. Split out so
:mod:`resilience_kit.ssrf.guard` stays focused on URL/DNS handling and
unit tests can parametrise the classifier directly.
"""

from __future__ import annotations

import ipaddress


def classify_non_public(addr: str) -> str | None:
    """Return the reason ``addr`` is non-public, or ``None`` if it is public.

    Categories rejected by the SSRF guard:

    * ``"private"`` — RFC1918 / RFC4193 / IPv4-mapped private space.
    * ``"loopback"`` — ``127.0.0.0/8`` / ``::1``.
    * ``"link_local"`` — ``169.254.0.0/16`` / ``fe80::/10``.
    * ``"reserved"`` — IANA-reserved blocks.
    * ``"unspecified"`` — ``0.0.0.0`` / ``::``.
    * ``"multicast"`` — ``224.0.0.0/4`` / ``ff00::/8``.

    The order is the public-facing label, not a precedence: an address
    that is both private and reserved still resolves to a single label
    via Python's :mod:`ipaddress` flags.

    Args:
        addr: Textual IPv4 or IPv6 address.

    Returns:
        A short category string when the address is non-public; ``None``
        when the address is a routable, public unicast address.

    Raises:
        ValueError: ``addr`` is not a valid textual IP address.
    """
    ip = ipaddress.ip_address(addr)
    # Order matters only for the public-facing label; an address with
    # multiple flags reports its most-specific reason first.
    for attr, label in (
        ("is_loopback", "loopback"),
        ("is_link_local", "link_local"),
        ("is_multicast", "multicast"),
        ("is_unspecified", "unspecified"),
        ("is_private", "private"),
        ("is_reserved", "reserved"),
    ):
        if getattr(ip, attr):
            return label
    return None


def is_non_public(addr: str) -> bool:
    """Return ``True`` when ``addr`` is in any non-public category.

    Args:
        addr: Textual IPv4 or IPv6 address.

    Returns:
        ``True`` for private / loopback / link-local / multicast /
        reserved / unspecified addresses; ``False`` for public unicast.

    Raises:
        ValueError: ``addr`` is not a valid textual IP address.
    """
    return classify_non_public(addr) is not None
