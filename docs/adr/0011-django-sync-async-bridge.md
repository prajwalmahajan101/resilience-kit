# 0011 — Django sync/async bridge

Status: proposed  ·  Date: 2026-06-10  ·  Milestone: M6

## Context

The kit is async-first: `AsyncBreaker`, `AsyncThrottle`, `AsyncCache`,
`RecoveryMonitor`, and the audit dispatcher all assume an asyncio event
loop. Django is sync-first: `AppConfig.ready()` runs synchronously on
process start (and again on autoreload), classic views and management
commands have no running loop, ASGI views have a loop per request, and
DRF throttle classes are called synchronously from the request lifecycle.

M6 must therefore translate between those two worlds without:

- starting a private loop inside an existing loop (refused upstream in
  `decorators.py` and `AsyncAPIClient.request_sync`);
- pinning the `RecoveryMonitor` to a per-request loop (it must outlive
  any single request and survive autoreload);
- silently dropping audit events because the dispatcher queue was bound
  to a closed loop.

This ADR documents the sync/async bridge pattern M6 commits to: where
private loops are spawned, which threads own them, and how DRF throttle
classes and management commands enter the async world without
re-entrancy hazards.

## Decision

_To be filled by the M6 execution branch (`feat/m6-django-adapter`)._

## Consequences

_To be filled by the M6 execution branch._

## Usage

_To be filled by the M6 execution branch._
