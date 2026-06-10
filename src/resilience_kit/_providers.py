"""Shared backend-provider resolution chain (LLD §3).

One helper, used by every swappable subsystem (cache / breaker / throttle /
audit / sanitizer / metrics / settings-source). Resolution order:

1. Explicit callable / instance — return as-is.
2. ``"pkg.mod:Class"`` importable string — import + instantiate.
3. ``name`` matches an entry point in the named group — load + instantiate.
4. ``name`` matches one of the kit's builtin names — instantiate.
5. Otherwise raise :class:`UnknownBackendError` with the list of available
   names so the failure message itself tells the operator what to set
   ``RESILIENCE_<SUBSYSTEM>_BACKEND`` to.

Backends gated behind a pip extra raise :class:`MissingExtraError` at
import time (not first use), so the failure is immediate and the hint is
unambiguous.

Precedence note (ADR 0004): entry points are checked **before** builtins
(step 3 before step 4). A third-party package that publishes an entry
point with the same name as a kit builtin therefore **shadows** the
builtin. This is intentional — it lets a third party ship a drop-in
replacement for ``memory`` / ``noop`` / ``stdlib_logging`` without
forking the kit — but it is also a footgun for accidental name
collisions. Operators should namespace third-party backend names
(``acme-redis``, not ``redis``) to avoid surprises. Documented in
``docs/LLD.md`` §3 and ``docs/adr/0004-entry-points-for-third-party-backends.md``.
"""

from __future__ import annotations

import importlib
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any, TypeVar

from resilience_kit.exceptions import UnknownBackendError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

T = TypeVar("T")


def resolve_provider(
    *,
    group: str,
    name: str | T | Callable[..., T],
    builtins: Mapping[str, Callable[..., T]],
    factory_kwargs: Mapping[str, Any] | None = None,
) -> T:
    """Resolve a backend instance via the 5-step chain in this module's docstring.

    Args:
        group: Entry-point group queried (e.g. ``"resilience_kit.cache_backends"``).
        name: Explicit instance / callable, importable ``"mod:Class"`` string,
            entry-point name, or builtin name.
        builtins: Mapping of builtin names → callables that produce a backend.
        factory_kwargs: Optional kwargs threaded into the factory call when
            ``name`` resolves to a callable (string / entry-point / builtin
            cases). Pre-built instances pass through unchanged.

    Returns:
        The resolved backend.

    Raises:
        UnknownBackendError: ``name`` is a string but does not resolve via
            entry-point or builtin.
        TypeError: ``name`` is a string with ``":"`` but the import target
            is not a callable.
    """
    kwargs: Mapping[str, Any] = factory_kwargs or {}

    # 1. Explicit instance — anything that is not a string is treated as
    # either a ready-made instance or a no-arg factory the caller wants to
    # use as-is.
    if not isinstance(name, str):
        return name(**kwargs) if callable(name) else name

    # 2. Importable string "pkg.mod:Class".
    if ":" in name:
        module_path, _, attr = name.partition(":")
        module = importlib.import_module(module_path)
        target = getattr(module, attr)
        if not callable(target):
            raise TypeError(
                f"Importable string {name!r} resolved to a non-callable "
                f"({type(target).__name__}); expected a class or factory.",
            )
        return target(**kwargs)  # type: ignore[no-any-return]

    # 3. Entry-point lookup.
    for ep in entry_points(group=group):
        if ep.name == name:
            target = ep.load()
            return target(**kwargs)  # type: ignore[no-any-return]

    # 4. Builtin.
    if name in builtins:
        return builtins[name](**kwargs)

    # 5. Fail with the list of options.
    available = sorted(
        {*builtins.keys(), *(ep.name for ep in entry_points(group=group))},
    )
    raise UnknownBackendError(group=group, name=name, available=available)
