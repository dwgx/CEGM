"""CEGM-namespaced MCP tools layered over the proxied surface.

This module owns the **CEGM extras** — every tool name here starts with
``cegm.`` (or, for runtime-defined tools, ``custom.``). Upstream's 175
tools come through verbatim and live behind whatever names miscusi-peek
chose. Our extras add three things upstream doesn't have:

  1. **State observability** — ``cegm.activity_recent``,
     ``cegm.dashboard_chat``.
  2. **RE workbench scaffolding** — ``cegm.scan*``, ``cegm.watch_*``,
     ``cegm.hex_dump``.
  3. **Self-extension** — ``cegm.tool_define``, ``cegm.tool_undefine``,
     ``cegm.tool_list_custom``, plus the dynamic dispatch path that
     turns a stored Lua snippet into a proxied ``evaluate_lua`` call.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Final

from mcp import types

from cegm_broker._logging import get_logger
from cegm_broker.dynamic_tools import DynamicToolRegistry
from cegm_broker.event_bus import Event, EventBus
from cegm_broker.scans import ScanRegistry
from cegm_broker.watches import WatchRegistry

if TYPE_CHECKING:
    from cegm_broker.mcp_proxy import MCPProxy

_log = get_logger(__name__)

_VT_DEFAULT: Final[str] = "int32"
_ASCII_PRINTABLE_MIN: Final[int] = 0x20  # space
_ASCII_PRINTABLE_MAX: Final[int] = 0x7E  # tilde
_HEX_CHARS_PER_ROW: Final[int] = 32  # 16 bytes


def _vt_to_upstream_type(vt: str) -> str:
    """Map our slug to miscusi-peek's ``type`` string for ``scan_all``."""
    table = {
        "byte": "byte",
        "int8": "byte",
        "word": "smallint",
        "int16": "smallint",
        "dword": "integer",
        "int": "integer",
        "int32": "integer",
        "uint": "integer",
        "uint32": "integer",
        "qword": "int64",
        "int64": "int64",
        "float": "single",
        "double": "double",
        "string": "string",
    }
    return table.get(vt.lower(), "integer")


# ── static tool definitions ──────────────────────────────────────────

EXTRAS_TOOL_DEFS: Final[list[types.Tool]] = [
    types.Tool(
        name="cegm.activity_recent",
        description=(
            "Return the most recent CEGM events (tool calls, chat turns, "
            "preview/snapshot lifecycle, broker/CE status). Use when you "
            "need to recall what just happened without re-running tools."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 50,
                },
            },
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.dashboard_chat",
        description=(
            "Hand off a chat message to the CEGM browser dashboard. The "
            "broker broadcasts a 'dashboard_chat_request' event over its "
            "WebSocket so any open dashboard tab auto-submits the message "
            "as if the user had typed it. Use when you want the user to "
            "take over the conversation in their browser."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "minLength": 1},
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.scan",
        description=(
            "First-scan: search the attached process for ``value`` of "
            "type ``vt`` and return a fresh scan_id along with the first "
            "page of hit addresses. Wraps upstream ``scan_all`` + "
            "``get_scan_results`` in one round-trip so you don't have to "
            "follow up with a paging call. Snapshot of the first page is "
            "kept on the broker so the dashboard can re-render it."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "value": {"type": "string", "description": "value to scan for"},
                "vt": {
                    "type": "string",
                    "default": _VT_DEFAULT,
                    "description": "byte/word/dword/qword/float/double/string/int32/…",
                },
                "max_results": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500,
                },
                "protection": {
                    "type": "string",
                    "default": "+W-C",
                    "description": "memory-protection mask passed to upstream scan_all",
                },
            },
            "required": ["value"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.scan_narrow",
        description=(
            "Narrow the most recent scan. Wraps upstream ``next_scan`` "
            "with the same paging helper as ``cegm.scan``. ``op`` defaults "
            "to ``exact`` (the new value); ``increased`` / ``decreased`` "
            "/ ``changed`` / ``unchanged`` work without ``value``."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "default": "exact",
                    "enum": [
                        "exact",
                        "bigger",
                        "smaller",
                        "between",
                        "increased",
                        "decreased",
                        "changed",
                        "unchanged",
                    ],
                },
                "value": {
                    "type": "string",
                    "description": "required when op needs a comparison value",
                },
                "max_results": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.scan_drop",
        description=(
            "Forget the most recent scan record. UI hygiene only; "
            "doesn't release the upstream MemScan."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "scan_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.watch_add",
        description=(
            "Register an address as a live watch. The broker polls it "
            "every ~250 ms and emits ``watch_update`` events on every "
            "change so the dashboard can render a live grid. Idempotent "
            "on (address, vt) — adding the same pair twice updates the "
            "label."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "address": {"type": "string"},
                "vt": {"type": "string", "default": _VT_DEFAULT},
                "label": {"type": "string", "default": ""},
            },
            "required": ["address"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.watch_remove",
        description="Stop watching an address. ``key`` may be a watch_id or the literal address.",
        inputSchema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.watch_list",
        description="List all currently-active watches.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="cegm.hex_dump",
        description=(
            "Read a region of the attached process and return rows of "
            "16 bytes formatted as offset / hex / ASCII. Useful for "
            "structure dissection without firing up CE's memory view."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "address": {"type": "string"},
                "length": {"type": "integer", "default": 64, "minimum": 1, "maximum": 4096},
            },
            "required": ["address"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.tool_define",
        description=(
            "Register a runtime-defined tool. The Lua body runs inside "
            "CE's Lua engine each time the tool is called, with the call "
            "arguments available as the global ``params``. Names MUST "
            "start with ``custom.`` so they never collide with the static "
            "tool surface. Persists to %LOCALAPPDATA%\\CEGM\\dynamic_tools.json "
            "so definitions survive restarts."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^custom\\.[A-Za-z_][A-Za-z0-9_.-]*$",
                    "description": "must start with custom.",
                },
                "description": {"type": "string"},
                "input_schema": {
                    "type": "object",
                    "description": "JSON Schema for this tool's input. Empty object = no params.",
                },
                "lua_body": {
                    "type": "string",
                    "description": (
                        "Lua snippet executed via evaluate_lua. ``params`` is the args table."
                    ),
                    "minLength": 1,
                },
            },
            "required": ["name", "lua_body"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.tool_undefine",
        description="Remove a previously-defined custom tool.",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.tool_list_custom",
        description="List runtime-defined tools currently registered with the broker.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
]


def is_extra(name: str) -> bool:
    """``True`` if ``name`` is one of CEGM's static or runtime tools."""
    return name.startswith("cegm.") or DynamicToolRegistry.is_dynamic_name(name)


# ── helpers ──────────────────────────────────────────────────────────


def _text(payload: dict[str, Any]) -> Sequence[types.ContentBlock]:
    return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _parse_upstream_payload(content: Sequence[types.ContentBlock]) -> dict[str, Any]:
    """Pull the first text block from a CallToolResult and JSON-parse it."""
    for block in content:
        if isinstance(block, types.TextContent):
            try:
                parsed: Any = json.loads(block.text)
            except json.JSONDecodeError:
                return {"raw": block.text}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
    return {}


async def _upstream_call(proxy: MCPProxy, name: str, args: dict[str, Any]) -> dict[str, Any]:
    if not proxy.available:
        raise RuntimeError("upstream MCP proxy is not connected")
    res = await proxy.call_tool(name, args)
    return _parse_upstream_payload(res.content)


# ── dispatch ─────────────────────────────────────────────────────────


async def dispatch(  # noqa: PLR0911, PLR0912, PLR0915 — single fan-out by tool name
    name: str,
    arguments: dict[str, Any],
    *,
    bus: EventBus,
    proxy: MCPProxy | None = None,
    scans: ScanRegistry | None = None,
    watches: WatchRegistry | None = None,
    dynamic: DynamicToolRegistry | None = None,
) -> Sequence[types.ContentBlock]:
    """Execute a CEGM extra (or custom) tool. Raises ``KeyError`` on unknown name."""

    if name == "cegm.activity_recent":
        limit = int(arguments.get("limit", 50))
        events = bus.recent(limit)
        return _text({"events": events, "count": len(events)})

    if name == "cegm.dashboard_chat":
        msg = arguments.get("message")
        if not isinstance(msg, str) or not msg.strip():
            raise ValueError("'message' must be a non-empty string")
        evt = Event.make("dashboard_chat_request", {"message": msg})
        await bus.publish(evt)
        return _text(
            {
                "ok": True,
                "url": "http://127.0.0.1:27077/",
                "delivered_at": evt["ts"],
                "dashboard_subscribers": bus.subscriber_count,
                "note": (
                    "Message broadcast to all open dashboard tabs. They will auto-submit it. "
                    "If subscribers is 0, tell the user to visit the URL."
                ),
            }
        )

    if name == "cegm.scan":
        if proxy is None or scans is None:
            raise RuntimeError("cegm.scan requires a configured proxy + scan registry")
        value = str(arguments.get("value", ""))
        if not value:
            raise ValueError("'value' is required")
        vt = str(arguments.get("vt", _VT_DEFAULT))
        max_results = int(arguments.get("max_results", 50))
        protection = str(arguments.get("protection", "+W-C"))
        upstream_type = _vt_to_upstream_type(vt)
        scan_summary = await _upstream_call(
            proxy,
            "scan_all",
            {"value": value, "type": "exact", "protection": protection},
        )
        count = int(scan_summary.get("count", 0))
        page = await _upstream_call(
            proxy,
            "get_scan_results",
            {"offset": 0, "limit": max_results},
        )
        results = list(page.get("results", []))[:max_results]
        rec = scans.record(
            value=value,
            vt=vt,
            op="exact",
            count=count,
            results=results,
            note=f"upstream type={upstream_type} protection={protection}",
        )
        await bus.publish(
            Event.make(
                "scan_started",
                {
                    "scan_id": rec.scan_id,
                    "value": value,
                    "vt": vt,
                    "count": count,
                    "page_size": rec.page_size,
                },
            )
        )
        return _text(
            {
                "scan_id": rec.scan_id,
                "value": value,
                "vt": vt,
                "count": count,
                "page_size": rec.page_size,
                "results": results,
            }
        )

    if name == "cegm.scan_narrow":
        if proxy is None or scans is None:
            raise RuntimeError("cegm.scan_narrow requires a configured proxy + scan registry")
        latest = scans.latest()
        if latest is None:
            raise ValueError("no active scan to narrow; call cegm.scan first")
        op = str(arguments.get("op", "exact"))
        max_results = int(arguments.get("max_results", 50))
        narrow_value_raw = arguments.get("value")
        narrow_value: str | None = None if narrow_value_raw is None else str(narrow_value_raw)
        upstream_args: dict[str, Any] = {"type": op}
        if narrow_value is not None:
            upstream_args["value"] = narrow_value
        narrow_summary = await _upstream_call(proxy, "next_scan", upstream_args)
        count = int(narrow_summary.get("count", 0))
        page = await _upstream_call(proxy, "get_scan_results", {"offset": 0, "limit": max_results})
        results = list(page.get("results", []))[:max_results]
        rec = scans.record(
            value=narrow_value if narrow_value is not None else f"({op})",
            vt=latest.vt,
            op=op,
            count=count,
            results=results,
            parent_id=latest.scan_id,
        )
        await bus.publish(
            Event.make(
                "scan_narrowed",
                {
                    "scan_id": rec.scan_id,
                    "parent_id": latest.scan_id,
                    "op": op,
                    "count": count,
                    "page_size": rec.page_size,
                },
            )
        )
        return _text(
            {
                "scan_id": rec.scan_id,
                "parent_id": latest.scan_id,
                "op": op,
                "count": count,
                "page_size": rec.page_size,
                "results": results,
            }
        )

    if name == "cegm.scan_drop":
        if scans is None:
            raise RuntimeError("cegm.scan_drop requires a scan registry")
        scan_id = str(arguments.get("scan_id", ""))
        if not scan_id:
            latest = scans.latest()
            if latest is None:
                return _text({"removed": False, "reason": "no scans to drop"})
            scan_id = latest.scan_id
        ok = scans.remove(scan_id)
        await bus.publish(Event.make("scan_dropped", {"scan_id": scan_id, "ok": ok}))
        return _text({"removed": ok, "scan_id": scan_id})

    if name == "cegm.watch_add":
        if watches is None:
            raise RuntimeError("cegm.watch_add requires a watch registry")
        address = str(arguments.get("address", ""))
        if not address:
            raise ValueError("'address' is required")
        vt = str(arguments.get("vt", _VT_DEFAULT))
        label = str(arguments.get("label", ""))
        w = watches.add(address=address, vt=vt, label=label)
        await bus.publish(
            Event.make(
                "watch_added",
                {"watch_id": w.watch_id, "address": w.address, "vt": w.vt, "label": w.label},
            )
        )
        return _text({"watch_id": w.watch_id, "address": w.address, "vt": w.vt, "label": w.label})

    if name == "cegm.watch_remove":
        if watches is None:
            raise RuntimeError("cegm.watch_remove requires a watch registry")
        key = str(arguments.get("key", ""))
        if not key:
            raise ValueError("'key' is required")
        ok = watches.remove(key)
        if ok:
            await bus.publish(Event.make("watch_removed", {"key": key}))
        return _text({"removed": ok, "key": key})

    if name == "cegm.watch_list":
        if watches is None:
            raise RuntimeError("cegm.watch_list requires a watch registry")
        out = [
            {
                "watch_id": w.watch_id,
                "address": w.address,
                "vt": w.vt,
                "label": w.label,
                "last_value": w.last_value,
                "last_seen_ts": w.last_seen_ts,
                "error": w.error,
            }
            for w in watches.list()
        ]
        return _text({"watches": out, "count": len(out)})

    if name == "cegm.hex_dump":
        if proxy is None:
            raise RuntimeError("cegm.hex_dump requires a configured proxy")
        address = str(arguments.get("address", ""))
        if not address:
            raise ValueError("'address' is required")
        length = int(arguments.get("length", 64))
        upstream = await _upstream_call(
            proxy, "read_memory", {"address": address, "length": length}
        )
        # Upstream's payload field varies by tool version: ``data`` (hex
        # string with spaces) is what we see in v12; ``hex`` / ``bytes``
        # / ``result`` are fallbacks for older builds.
        hex_str = upstream.get("data") or upstream.get("hex") or upstream.get("result", "")
        if not isinstance(hex_str, str):
            hex_str = ""
        cleaned = hex_str.replace(" ", "").replace("\n", "").lower()
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(cleaned), _HEX_CHARS_PER_ROW):
            chunk = cleaned[offset : offset + _HEX_CHARS_PER_ROW]
            byte_pairs = [chunk[i : i + 2] for i in range(0, len(chunk), 2)]
            ascii_repr = "".join(
                chr(int(b, 16))
                if b and _ASCII_PRINTABLE_MIN <= int(b, 16) <= _ASCII_PRINTABLE_MAX
                else "."
                for b in byte_pairs
            )
            rows.append(
                {
                    "offset": offset // 2,
                    "hex": " ".join(byte_pairs),
                    "ascii": ascii_repr,
                }
            )
        return _text({"address": address, "length": length, "rows": rows, "raw_upstream": upstream})

    if name == "cegm.tool_define":
        if dynamic is None:
            raise RuntimeError("cegm.tool_define requires a dynamic-tool registry")
        try:
            tool = dynamic.define(
                name=str(arguments.get("name", "")),
                description=str(arguments.get("description", "")),
                input_schema=dict(
                    arguments.get("input_schema") or {"type": "object", "properties": {}}
                ),
                lua_body=str(arguments.get("lua_body", "")),
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        await bus.publish(
            Event.make("dynamic_tool_defined", {"name": tool.name, "updated_at": tool.updated_at})
        )
        return _text({"ok": True, "tool": asdict(tool)})

    if name == "cegm.tool_undefine":
        if dynamic is None:
            raise RuntimeError("cegm.tool_undefine requires a dynamic-tool registry")
        target = str(arguments.get("name", ""))
        ok = dynamic.undefine(target)
        if ok:
            await bus.publish(Event.make("dynamic_tool_undefined", {"name": target}))
        return _text({"removed": ok, "name": target})

    if name == "cegm.tool_list_custom":
        if dynamic is None:
            raise RuntimeError("cegm.tool_list_custom requires a dynamic-tool registry")
        return _text({"tools": [asdict(t) for t in dynamic.all()], "count": len(dynamic.all())})

    # Custom-tool dispatch — render the body into evaluate_lua.
    if dynamic is not None and dynamic.is_dynamic_name(name):
        if proxy is None:
            raise RuntimeError("custom tool dispatch requires a configured proxy")
        custom = dynamic.get(name)
        if custom is None:
            raise KeyError(f"custom tool not registered: {name!r}")
        wrapped = DynamicToolRegistry.render_invocation(custom, arguments)
        upstream = await _upstream_call(proxy, "evaluate_lua", {"code": wrapped})
        await bus.publish(
            Event.make(
                "dynamic_tool_called",
                {"name": name, "args": arguments, "result_preview": str(upstream)[:200]},
            )
        )
        return _text({"ok": True, "tool": name, "result": upstream})

    raise KeyError(f"unknown CEGM tool: {name!r}")
