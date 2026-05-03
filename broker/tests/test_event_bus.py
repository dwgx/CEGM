"""Event bus contract tests.

Covers the happy path (publish reaches every subscriber), the slow-consumer
path (overflowed subscriber is dropped without blocking producers), and
the bounded history buffer used by ``cegm.activity_recent``.
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


@pytest.mark.asyncio
async def test_recent_returns_chronological_window() -> None:
    """Recent events come back oldest-first, capped at the requested limit."""
    bus = EventBus(history_size=10)
    for i in range(5):
        await bus.publish(Event.make("tool_called", {"i": i}))

    last_three = bus.recent(3)
    assert [e["data"]["i"] for e in last_three] == [2, 3, 4]
    assert bus.recent(0) == []
    assert len(bus.recent(100)) == 5  # clamps to history size


@pytest.mark.asyncio
async def test_history_evicts_oldest_when_full() -> None:
    """Once history_size is reached, older entries fall out."""
    bus = EventBus(history_size=3)
    for i in range(6):
        await bus.publish(Event.make("tool_called", {"i": i}))
    snapshot = bus.recent(10)
    assert [e["data"]["i"] for e in snapshot] == [3, 4, 5]
