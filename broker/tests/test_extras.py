"""CEGM-namespaced tool dispatch tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import types

from cegm_broker.dynamic_tools import DynamicToolRegistry
from cegm_broker.event_bus import Event, EventBus
from cegm_broker.mcp_extras import EXTRAS_TOOL_DEFS, dispatch, is_extra
from cegm_broker.scans import ScanRegistry
from cegm_broker.watches import WatchRegistry


def test_extras_tool_defs_are_namespaced() -> None:
    """Every shipped extra is named ``cegm.*``."""
    assert all(t.name.startswith("cegm.") for t in EXTRAS_TOOL_DEFS)


def test_is_extra_classifies_correctly() -> None:
    assert is_extra("cegm.activity_recent")
    assert is_extra("custom.my_helper")
    assert not is_extra("read_memory")
    assert not is_extra("aob_scan")


# ── activity_recent / dashboard_chat (already shipped) ────────────────


@pytest.mark.asyncio
async def test_activity_recent_returns_history_as_text() -> None:
    bus = EventBus(history_size=10)
    await bus.publish(Event.make("tool_called", {"name": "read_memory"}))
    await bus.publish(Event.make("tool_result", {"name": "read_memory", "ok": True}))

    content = await dispatch("cegm.activity_recent", {"limit": 5}, bus=bus)
    assert len(content) == 1
    block = content[0]
    assert isinstance(block, types.TextContent)
    payload = json.loads(block.text)
    assert payload["count"] == 2
    assert payload["events"][-1]["kind"] == "tool_result"


@pytest.mark.asyncio
async def test_activity_recent_default_limit() -> None:
    bus = EventBus(history_size=200)
    for i in range(60):
        await bus.publish(Event.make("tool_called", {"i": i}))
    content = await dispatch("cegm.activity_recent", {}, bus=bus)
    payload = json.loads(content[0].text)  # type: ignore[union-attr]
    assert payload["count"] == 50
    assert payload["events"][-1]["data"]["i"] == 59


@pytest.mark.asyncio
async def test_unknown_extra_raises() -> None:
    bus = EventBus()
    with pytest.raises(KeyError):
        await dispatch("cegm.does_not_exist", {}, bus=bus)


@pytest.mark.asyncio
async def test_dashboard_chat_publishes_event() -> None:
    bus = EventBus(history_size=10)
    content = await dispatch(
        "cegm.dashboard_chat",
        {"message": "find the HP value in notepad"},
        bus=bus,
    )
    payload = json.loads(content[0].text)  # type: ignore[union-attr]
    assert payload["ok"] is True
    assert payload["url"].startswith("http://127.0.0.1:")
    recent = bus.recent(5)
    msg = next(e for e in recent if e["kind"] == "dashboard_chat_request")
    assert msg["data"]["message"] == "find the HP value in notepad"


@pytest.mark.asyncio
async def test_dashboard_chat_rejects_empty_message() -> None:
    bus = EventBus()
    with pytest.raises(ValueError, match="non-empty"):
        await dispatch("cegm.dashboard_chat", {"message": ""}, bus=bus)
    with pytest.raises(ValueError, match="non-empty"):
        await dispatch("cegm.dashboard_chat", {"message": "   "}, bus=bus)


# ── scans (cegm.scan / scan_narrow / scan_drop) ──────────────────────


def _make_proxy(*upstream_results: dict[str, object]) -> MagicMock:
    """Build a fake MCPProxy whose ``call_tool`` returns canned payloads in order."""
    proxy = MagicMock()
    proxy.available = True

    queue = list(upstream_results)

    async def _call(name: str, args: dict[str, object]) -> object:
        payload = queue.pop(0) if queue else {}
        block = types.TextContent(type="text", text=json.dumps(payload))
        result = MagicMock()
        result.content = [block]
        return result

    proxy.call_tool = AsyncMock(side_effect=_call)
    return proxy


@pytest.mark.asyncio
async def test_scan_returns_first_page_inline() -> None:
    bus = EventBus()
    scans = ScanRegistry()
    proxy = _make_proxy(
        {"count": 17, "success": True},  # scan_all
        {"results": [{"address": "0xA", "value": "100"}], "total": 17},  # get_scan_results
    )
    content = await dispatch(
        "cegm.scan",
        {"value": "100"},
        bus=bus,
        proxy=proxy,
        scans=scans,
    )
    payload = json.loads(content[0].text)  # type: ignore[union-attr]
    assert payload["count"] == 17
    assert payload["results"][0]["address"] == "0xA"
    assert scans.latest() is not None


@pytest.mark.asyncio
async def test_scan_narrow_uses_latest_scan() -> None:
    bus = EventBus()
    scans = ScanRegistry()
    proxy = _make_proxy(
        {"count": 3, "success": True},  # scan_all
        {"results": [{"address": "0xA", "value": "100"}], "total": 3},  # page
        {"count": 1, "success": True},  # next_scan
        {"results": [{"address": "0xA", "value": "95"}], "total": 1},  # page
    )
    await dispatch("cegm.scan", {"value": "100"}, bus=bus, proxy=proxy, scans=scans)
    parent = scans.latest()
    content = await dispatch(
        "cegm.scan_narrow",
        {"op": "exact", "value": "95"},
        bus=bus,
        proxy=proxy,
        scans=scans,
    )
    payload = json.loads(content[0].text)  # type: ignore[union-attr]
    assert payload["count"] == 1
    assert payload["parent_id"] == (parent.scan_id if parent else "")


@pytest.mark.asyncio
async def test_scan_narrow_without_active_scan_raises() -> None:
    bus = EventBus()
    scans = ScanRegistry()
    proxy = _make_proxy()
    with pytest.raises(ValueError, match="no active scan"):
        await dispatch("cegm.scan_narrow", {}, bus=bus, proxy=proxy, scans=scans)


# ── watches ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_watch_add_remove_list_round_trip() -> None:
    bus = EventBus()

    async def reader(_addr: str, _vt: str) -> object:
        return 0

    watches = WatchRegistry(bus=bus, reader=reader)

    add_content = await dispatch(
        "cegm.watch_add",
        {"address": "0x1234", "vt": "int32", "label": "HP"},
        bus=bus,
        watches=watches,
    )
    add = json.loads(add_content[0].text)  # type: ignore[union-attr]
    assert add["address"] == "0x1234"
    assert add["watch_id"].startswith("watch-")

    list_content = await dispatch("cegm.watch_list", {}, bus=bus, watches=watches)
    listed = json.loads(list_content[0].text)  # type: ignore[union-attr]
    assert listed["count"] == 1
    assert listed["watches"][0]["label"] == "HP"

    rm = await dispatch("cegm.watch_remove", {"key": "0x1234"}, bus=bus, watches=watches)
    assert json.loads(rm[0].text)["removed"] is True  # type: ignore[union-attr]
    final = await dispatch("cegm.watch_list", {}, bus=bus, watches=watches)
    assert json.loads(final[0].text)["count"] == 0  # type: ignore[union-attr]


# ── hex_dump ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hex_dump_groups_into_16_byte_rows() -> None:
    bus = EventBus()
    proxy = _make_proxy({"hex": "48656C6C6F2C20576F726C64210A41420000"})
    content = await dispatch(
        "cegm.hex_dump",
        {"address": "0x1000", "length": 18},
        bus=bus,
        proxy=proxy,
    )
    payload = json.loads(content[0].text)  # type: ignore[union-attr]
    assert payload["address"] == "0x1000"
    assert len(payload["rows"]) == 2  # 16 + 2
    assert "Hello, World!" in payload["rows"][0]["ascii"]


# ── dynamic tools ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_define_then_list_then_undefine(tmp_path: Path) -> None:
    bus = EventBus()
    dynamic = DynamicToolRegistry(storage_path=tmp_path / "dynamic_tools.json")

    define_content = await dispatch(
        "cegm.tool_define",
        {
            "name": "custom.read_dword",
            "description": "Read a DWORD from an address",
            "input_schema": {
                "type": "object",
                "properties": {"address": {"type": "string"}},
                "required": ["address"],
            },
            "lua_body": "return readInteger(params.address)",
        },
        bus=bus,
        dynamic=dynamic,
    )
    payload = json.loads(define_content[0].text)  # type: ignore[union-attr]
    assert payload["ok"] is True
    assert payload["tool"]["name"] == "custom.read_dword"

    list_content = await dispatch("cegm.tool_list_custom", {}, bus=bus, dynamic=dynamic)
    listed = json.loads(list_content[0].text)  # type: ignore[union-attr]
    assert listed["count"] == 1

    undef = await dispatch(
        "cegm.tool_undefine", {"name": "custom.read_dword"}, bus=bus, dynamic=dynamic
    )
    assert json.loads(undef[0].text)["removed"] is True  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_tool_define_rejects_non_custom_namespace(tmp_path: Path) -> None:
    bus = EventBus()
    dynamic = DynamicToolRegistry(storage_path=tmp_path / "dynamic_tools.json")
    with pytest.raises(ValueError, match="custom\\."):
        await dispatch(
            "cegm.tool_define",
            {"name": "tools.evil", "lua_body": "print('x')"},
            bus=bus,
            dynamic=dynamic,
        )
