"""Unit tests for :mod:`resilience_kit.audit.decorators`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resilience_kit.audit import (
    AuditEvent,
    log_inbound,
    log_outbound,
    set_dispatcher,
)
from resilience_kit.audit.dispatch import InlineDispatcher
from resilience_kit.context import bind

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence


class _CollectingBackend:
    def __init__(self) -> None:
        self.batches: list[list[AuditEvent]] = []

    async def write_many(self, events: Sequence[AuditEvent]) -> None:
        self.batches.append(list(events))

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def collecting() -> Iterator[_CollectingBackend]:
    backend = _CollectingBackend()
    dispatcher = InlineDispatcher(backend)
    set_dispatcher(dispatcher)
    return backend


@pytest.mark.asyncio
async def test_log_inbound_async_success_event(collecting: _CollectingBackend) -> None:
    """Successful async call emits an inbound success event."""

    @log_inbound("api", method="POST", path="/v1/create")
    async def handler(*, x: int) -> int:
        return x * 2

    assert await handler(x=21) == 42
    # Trigger flush from the inline dispatcher.
    dispatcher = InlineDispatcher.__init__
    _ = dispatcher  # silence unused
    from resilience_kit.audit import get_dispatcher  # noqa: PLC0415

    await get_dispatcher().aclose()  # type: ignore[attr-defined]

    assert collecting.batches
    event = collecting.batches[0][0]
    assert event.direction == "inbound"
    assert event.service == "api"
    assert event.outcome == "success"
    assert event.method == "POST"
    assert event.error_class is None


@pytest.mark.asyncio
async def test_log_inbound_async_failure_event(collecting: _CollectingBackend) -> None:
    """A raise inside an async handler emits a failure event then re-raises."""

    @log_inbound("api", method="GET", path="/v1/x")
    async def handler() -> None:
        msg = "nope"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="nope"):
        await handler()

    from resilience_kit.audit import get_dispatcher  # noqa: PLC0415

    await get_dispatcher().aclose()  # type: ignore[attr-defined]

    assert collecting.batches
    event = collecting.batches[0][0]
    assert event.outcome == "failure"
    assert event.error_class == "ValueError"


def test_log_outbound_sync_success(collecting: _CollectingBackend) -> None:
    """Sync outbound capture works and propagates the call's return value."""

    @log_outbound("partner", method="GET", path="/v1/x")
    def call() -> str:
        return "ok"

    assert call() == "ok"
    import asyncio  # noqa: PLC0415

    from resilience_kit.audit import get_dispatcher  # noqa: PLC0415

    asyncio.run(get_dispatcher().aclose())  # type: ignore[attr-defined]
    assert collecting.batches
    event = collecting.batches[0][0]
    assert event.direction == "outbound"
    assert event.outcome == "success"


@pytest.mark.asyncio
async def test_log_inbound_reads_context_vars(collecting: _CollectingBackend) -> None:
    """The event picks up request_id / correlation_id from the ContextVars."""

    @log_inbound("api", method="POST", path="/v1/x")
    async def handler() -> None:
        return None

    with bind(request_id_value="rq-1", correlation_id_value="corr-1"):
        await handler()

    from resilience_kit.audit import get_dispatcher  # noqa: PLC0415

    await get_dispatcher().aclose()  # type: ignore[attr-defined]
    event = collecting.batches[0][0]
    assert event.request_id == "rq-1"
    assert event.correlation_id == "corr-1"


@pytest.mark.asyncio
async def test_payload_factory_runs_and_is_redacted(
    collecting: _CollectingBackend,
) -> None:
    """The payload_factory result lands sanitised in the event payload."""

    def factory(*, body: dict[str, str]) -> dict[str, str]:
        return body

    @log_inbound("api", method="POST", path="/v1/x", payload_factory=factory)
    async def handler(*, body: dict[str, str]) -> None:
        return None

    await handler(body={"password": "p", "user": "alice"})

    from resilience_kit.audit import get_dispatcher  # noqa: PLC0415

    await get_dispatcher().aclose()  # type: ignore[attr-defined]
    event = collecting.batches[0][0]
    assert event.payload["password"] == "[REDACTED]"
    assert event.payload["user"] == "alice"


@pytest.mark.asyncio
async def test_payload_factory_error_is_swallowed(
    collecting: _CollectingBackend,
) -> None:
    """If the payload_factory raises, the audit event still goes out with {}."""

    def bad_factory(**_kwargs: object) -> dict[str, str]:
        msg = "broken"
        raise RuntimeError(msg)

    @log_inbound("api", payload_factory=bad_factory)
    async def handler() -> None:
        return None

    await handler()
    from resilience_kit.audit import get_dispatcher  # noqa: PLC0415

    await get_dispatcher().aclose()  # type: ignore[attr-defined]
    assert collecting.batches
    assert collecting.batches[0][0].payload == {}
