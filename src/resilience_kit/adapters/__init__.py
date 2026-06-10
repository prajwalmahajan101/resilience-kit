"""Framework adapters.

Each adapter is pure glue between a web framework's lifecycle hooks and
the kit's framework-agnostic primitives (recovery monitor, audit
dispatcher, health aggregator, middleware, decorators). Adapters never
hold business logic; if an adapter file grows past ~300 LOC the
underlying primitive is wrong, not the adapter.

Sub-packages are extras-gated: importing
``resilience_kit.adapters.fastapi`` without the ``[fastapi]`` extra
raises :class:`~resilience_kit.exceptions.MissingExtraError`.
"""
