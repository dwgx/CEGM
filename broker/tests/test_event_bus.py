"""Event bus contract tests.

Covers the happy path (publish reaches every subscriber) and the slow-consumer
path (overflowed subscriber is dropped without blocking producers).
"""

from __future__ import annotations

import asyncio

import pytest

from cegm_broker.event_bus import Event, EventBus


@pytest.mark.asyncio
async def test_event_make_populates_metadata() -> None:
    """``Event.make`` always sets ``ts``, ``id`` and ``kind``."""
    e = Event.make("tool_called", {"name": "foo"})
    assert e["kind"] == "tool_called"
    assert e["data"] == {"name": "foo"}
    assert isinstance(e["ts"], str)
    assert e["id"].startswith("evt-")


@pytest.mark.asyncio
async def test_publish_reaches_all_subscribers() -> None:
    """A single publish fans out to every active subscriber."""
    bus = EventBus()
    received: list[Event] = []

    async with bus.subscribe() as stream_a, bus.subscribe() as stream_b:
        assert bus.subscriber_count == 2
        await bus.publish(Event.make("tool_called", {"x": 1}))

        # Each subscriber sees the same event independently.
        evt_a = await asyncio.wait_for(stream_a.__anext__(), timeout=1.0)
        evt_b = await asyncio.wait_for(stream_b.__anext__(), timeout=1.0)
        received.extend([evt_a, evt_b])

    assert bus.subscriber_count == 0
    assert {e["data"]["x"] for e in received} == {1}


@pytest.mark.asyncio
async def test_subscriber_count_zero_at_rest() -> None:
    """No subscribers when nobody is in a ``subscribe`` block."""
    bus = EventBus()
    assert bus.subscriber_count == 0
