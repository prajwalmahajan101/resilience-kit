# M8b upgrade — boilerplate intake summary

Synthesizes the two reports filed at the end of the `0.1.0rc1` → `0.1.0`
upgrade cycle. Both reports met the ≥ 8/10 outcome gate from
[`docs/RELEASE-PLAN.md`](../RELEASE-PLAN.md), so v0.1.0 is officially
"clean-cut" by the kit's own criteria. The findings below are the v0.1.x
and v0.2 ROADMAP signal.

## Reports filed

| Repo | Score | Date | Source |
|---|---|---|---|
| [`fastapi_boilerplate`](./fastapi_boilerplate.md) | **8 / 10** | 2026-06-10 | M7 + M8 dogfooding round 2 |
| [`django_boilerplate`](./django_boilerplate.md) | **9 / 10** | 2026-06-11 | M7 + M8 dogfooding round 1 |

Both reports applied all four primary helpers
(`bind_to`, `from_exception`, `legacy_env_alias`, `verify_envelope_contract`).
FastAPI also used `reset_all_singletons_async`; Django deferred it
(sync test harness, no use case yet).

## Cross-cutting findings (both reports flagged)

Patch-line candidates — additive, no breaking surface.

| # | Finding | Target |
|---|---|---|
| **X1** | Public bridge lives at `resilience_kit.adapters._envelope.from_exception` — leading underscore reads as private. Either re-export at `resilience_kit.adapters` or rename the module. | v0.1.1 |
| **X2** | `verify_envelope_contract` raises a flat `AssertionError`. Pytest only shows the first failure; programmatic CI dashboards can't introspect a structured result. Return an `EnvelopeContractResult` (list of `(exc_class, ok, reason)`). | v0.1.1 |
| **X3** | `legacy_env_alias(aliases=...)` *replaces* the default table — adopters who want to extend with project-specific aliases must copy the default dict + add. Add `extra_aliases=` that merges, or document the copy-pattern explicitly. | v0.1.1 |
| **X4** | Migration guide (`docs/MIGRATION-rc1-to-v0.1.0.md`) has four documented gaps. See "Doc gaps" below. | v0.1.0 doc patch (this PR) |

## FastAPI-specific findings

| # | Finding | Target |
|---|---|---|
| F1 | `from_exception(envelope_cls=...)` projection writes `[{field, message}]` per detail entry — fails consumer envelopes whose error-list-item shape has additional required fields (FastAPI envelope's `ErrorDetail.code` required). Add `code=exc.error_code` to projected list items, or provide a per-entry callback hook. | v0.1.1 |
| F2 | Missing `resilience_kit.adapters.fastapi.create_health_router(checks, *, path, ...)` — boilerplate kept ~200 LOC of its own router factory. | v0.1.1 (already on patch-line) |
| F3 | `MetricsSink` cardinality contract still missing (~80 LOC shim kept locally). | v0.2 |

## Django-specific findings

| # | Finding | Target |
|---|---|---|
| D1 | `MIGRATION-rc1-to-v0.1.0.md` Appendix B lacks the `BindRequestIdMiddleware` snippet — FastAPI gets a worked example, Django does not. | v0.1.0 doc patch (this PR) |
| D2 | §3.4 `verify_envelope_contract` example shows `handler(...).body` (FastAPI shape); DRF response stores body at `.data`. | v0.1.0 doc patch (this PR) |
| D3 | §3.3 should explicitly call out that `legacy_env_alias()` placement is load-bearing (must run before any `pydantic-settings` instantiation, i.e. top of `settings/base.py`). | v0.1.0 doc patch (this PR) |
| D4 | `from_exception` writes `request_id=None` when no envelope_cls or when no kit-side bridge is in place — adopter handler must top up from their own ContextVar. Doc should call this out. | v0.1.0 doc patch (this PR) |

## Convergent v0.2 wishlist (both reports raised)

| Item | Status | Notes |
|---|---|---|
| `DjangoSettingsSource` reading `settings.RESILIENCE` | already on ROADMAP v0.2 | Both reports rank this P1 |
| `resilience_kit.utils.*` (log_sanitization, network, timing, function_logger, data) | already on ROADMAP v0.2 | Django repo lists 5 modules; FastAPI implied |
| `GlobalThrottle` (Valkey-Lua) | already on ROADMAP v0.2 | nginx covers belt for now |
| Free-function `metrics.record_*` shim over `MetricsSink` | already on ROADMAP v0.2 | Both reports |
| `HTTPAuditEvent(AuditEvent)` subclass | already on ROADMAP v0.3 | FastAPI report; Django implied via audit pipeline |
| Multi-alias Redis (`RESILIENCE_REDIS_URLS__<alias>`) | already on ROADMAP v0.3 | FastAPI explicit |
| `ResilienceKitError.details` as attribute (not `@property`) | new, v0.1.1 candidate | Django bridge had to shadow the property |
| Public `bind_to` doc page (ContextVar semantics, cleanup, nesting) | v0.1.0 doc patch (this PR) | FastAPI flagged |

## Doc gaps to patch in this PR

1. **§3.1 (B1 recipe)** — add a "no existing request-id middleware" worked example (a fresh `BindRequestIdMiddleware` whose only job is the bridge). Both reports needed this; FastAPI wrote one from scratch, Django wrote one from scratch.
2. **§3.1 (B1 recipe)** — Appendix B should include the Django `BindRequestIdMiddleware` snippet verbatim.
3. **§3.2 (B2 recipe)** — call out that `envelope_cls` projection may fail validation when the target envelope's error-list-item shape has required fields beyond `{field, message}`. Provide the "drop `envelope_cls`, translate manually" fallback explicitly.
4. **§3.3 (D-Env recipe)** — explicit "ordering is load-bearing" note. Must run at top of `settings/base.py` before any `pydantic-settings` instantiation.
5. **§3.3 (D-Env recipe)** — note that `aliases=` argument *replaces* the default table; show the merge pattern explicitly.
6. **§3.4 (envelope contract test)** — show the DRF shape (`.data`) next to the FastAPI shape (`.body`).
7. **§4 (adopter checklist)** — printable table of the `DEFAULT_ALIASES` mapping so operators can sanity-check their `.env*` files without reading the source.
8. **§3.1 / new sub-section** — document that `from_exception` writes `request_id=None` unless `bind_to(request_id_ctx)` is installed *and* the envelope declares a `request_id` field — adopter handler should top up from their own ContextVar if the bridge isn't fully wired.

## ROADMAP changes proposed in this PR

- Add four v0.1.1 patch-line candidates: X1 (rename `_envelope`), X2 (structured contract result), X3 (mergeable aliases), F1 (projection `code` field).
- Promote F2 (`create_health_router`) to v0.1.1 explicitly — currently sits on the existing patch line.
- Add v0.1.x candidate: `ResilienceKitError.details` as instance attribute (Django bridge cleanup).

## Outcome gate

> "v0.1.0 was a clean cut iff both boilerplate reports score ≥ 8/10."
> — `docs/RELEASE-PLAN.md` §4 verification

FastAPI 8/10, Django 9/10 — **gate met**. v0.1.0 is officially clean-cut.
The findings above feed v0.1.x and v0.2 planning, not v0.1.0 hygiene.
