"""CEGM-namespaced tool dispatch tests."""

from __future__ import annotations

import json

import pytest
from mcp import types

from cegm_broker.event_bus import Event, EventBus
from cegm_broker.mcp_extras import EXTRAS_TOOL_DEFS, dispatch, is_extra


def test_extras_tool_defs_are_namespaced() -> None:
    """Every shipped extra is named ``cegm.*``."""
    assert all(t.name.startswith("cegm.") for t in EXTRAS_TOOL_DEFS)


def test_is_extra_classifies_correctly() -> None:
    assert is_extra("cegm.activity_recent")
    assert not is_extra("read_memory")
    assert not is_extra("aob_scan")


@pytest.mark.asyncio
async def test_activity_recent_returns_history_as_text() -> None:
    """The dispatcher returns the recent event log as a JSON text block."""
    bus = EventBus(history_size=10)
    await bus.publish(Event.make("tool_called", {"name": "read_memory"}))
    await bus.publish(Event.make("tool_result", {"name": "read_memory", "ok": True}))

    content = await dispatch("cegm.activity_recent", {"limit": 5}, bus)
    assert len(content) == 1
    block = content[0]
    assert isinstance(block, types.TextContent)
    payload = json.loads(block.text)
    assert isinstance(payload, list)
    assert payload[-1]["kind"] == "tool_result"


@pytest.mark.asyncio
async def test_activity_recent_default_limit() -> None:
    """Omitting ``limit`` returns up to the default 50."""
    bus = EventBus(history_size=200)
    for i in range(60):
        await bus.publish(Event.make("tool_called", {"i": i}))
    content = await dispatch("cegm.activity_recent", {}, bus)
    payload = json.loads(content[0].text)  # type: ignore[union-attr]
    assert len(payload) == 50
    # The last entry is the most recent.
    assert payload[-1]["data"]["i"] == 59


@pytest.mark.asyncio
async def test_unknown_extra_raises() -> None:
    bus = EventBus()
    with pytest.raises(KeyError):
        await dispatch("cegm.does_not_exist", {}, bus)


@pytest.mark.asyncio
async def test_dashboard_chat_publishes_event() -> None:
    """``cegm.dashboard_chat`` puts a ``dashboard_chat_request`` event on the bus."""
    bus = EventBus(history_size=10)
    content = await dispatch(
        "cegm.dashboard_chat",
        {"message": "find the HP value in notepad"},
        bus,
    )
    assert len(content) == 1
    block = content[0]
    assert isinstance(block, types.TextContent)
    payload = json.loads(block.text)
    assert payload["ok"] is True
    assert payload["url"].startswith("http://127.0.0.1:")

    # The event itself reached the history buffer.
    recent = bus.recent(5)
    kinds = [e["kind"] for e in recent]
    assert "dashboard_chat_request" in kinds
    msg = next(e for e in recent if e["kind"] == "dashboard_chat_request")
    assert msg["data"]["message"] == "find the HP value in notepad"


@pytest.mark.asyncio
async def test_dashboard_chat_rejects_empty_message() -> None:
    bus = EventBus()
    with pytest.raises(ValueError, match="non-empty"):
        await dispatch("cegm.dashboard_chat", {"message": ""}, bus)
    with pytest.raises(ValueError, match="non-empty"):
        await dispatch("cegm.dashboard_chat", {"message": "   "}, bus)
    with pytest.raises(ValueError, match="non-empty"):
        await dispatch("cegm.dashboard_chat", {}, bus)
