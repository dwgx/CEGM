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

import contextlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Final

from mcp import types

from cegm_broker._logging import get_logger
from cegm_broker.dynamic_tools import DynamicToolRegistry
from cegm_broker.event_bus import Event, EventBus
from cegm_broker.groups import GroupRegistry
from cegm_broker.recipes import RecipeRegistry
from cegm_broker.scans import ScanRegistry
from cegm_broker.watches import WatchRegistry

if TYPE_CHECKING:
    from cegm_broker.mcp_proxy import MCPProxy

_log = get_logger(__name__)

_VT_DEFAULT: Final[str] = "int32"
_ASCII_PRINTABLE_MIN: Final[int] = 0x20  # space
_ASCII_PRINTABLE_MAX: Final[int] = 0x7E  # tilde
_HEX_CHARS_PER_ROW: Final[int] = 32  # 16 bytes
_MAX_IDENTIFY_CANDIDATES: Final[int] = 5


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
            "First-scan: search the attached process memory. If ``value`` "
            "is provided, performs an exact-value first scan. If ``value`` "
            "is empty or omitted, performs an 'unknown initial value' scan "
            "(use this when the value isn't shown as a number — e.g. a "
            "health bar, a speed slider, or a hidden stat). "
            "Returns a scan_id plus the first page of hit addresses. "
            "Wraps upstream ``scan_all`` + ``get_scan_results`` in one "
            "round-trip. Snapshot of the first page is kept on the broker "
            "so the dashboard can re-render it.\n\n"
            "After an unknown-initial scan, narrow with cegm.scan_narrow "
            "using op='changed', 'unchanged', 'increased', or 'decreased'."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "value": {
                    "type": "string",
                    "description": (
                        "value to scan for; omit or leave empty for unknown-initial-value scan"
                    ),
                },
                "vt": {
                    "type": "string",
                    "default": _VT_DEFAULT,
                    "description": "byte/word/dword/qword/float/double/string/int32/...",
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
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.scan_narrow",
        description=(
            "Narrow the most recent scan. Wraps upstream ``next_scan`` "
            "with the same paging helper as ``cegm.scan``.\n\n"
            "For exact-value scans: use op='exact' with a value.\n"
            "For unknown-initial scans: use op='changed' (value changed "
            "since last scan), 'unchanged' (value stayed the same), "
            "'increased' (value went up), or 'decreased' (value went "
            "down). These do not need a ``value`` argument.\n\n"
            "Typical unknown-init narrowing sequence:\n"
            "  1. cegm.scan (no value) → 'Now change the value in-game'\n"
            "  2. cegm.scan_narrow(op='changed') → 'Now don't change anything'\n"
            "  3. cegm.scan_narrow(op='unchanged') → repeat until ≤5 hits"
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
                    "description": (
                        "required when op needs a comparison "
                        "value (exact, bigger, smaller, between)"
                    ),
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
            "Add an address to the live watch list. The broker polls it "
            "every ~250ms and the dashboard shows the value in a live grid. "
            "Use this to confirm you found the right address: add a few "
            "candidate addresses as watches, ask the user to change the "
            "value in-game, and see which watch tracks the change.\n\n"
            "Once confirmed, use cegm.watch_freeze to lock the value.\n"
            "Use cegm.watch_remove to clean up wrong candidates.\n\n"
            "Idempotent on (address, vt) — re-adding with a new label "
            "just updates the label."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "hex address like '0x1A2B3C4D' or 'module.exe+0x1234'",
                },
                "vt": {
                    "type": "string",
                    "default": _VT_DEFAULT,
                    "description": "value type: int32, float, double, int64, byte, string, etc.",
                },
                "label": {
                    "type": "string",
                    "default": "",
                    "description": "human-readable label like 'HP' or 'Gold'",
                },
            },
            "required": ["address"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.watch_freeze",
        description=(
            "Lock a watched address to a fixed value. The broker will "
            "re-write this value every ~250ms whenever the in-game value "
            "deviates. This is how you create 'infinite HP', 'unlimited "
            "ammo', etc. The address must already be watched via "
            "cegm.watch_add. ``key`` may be a watch_id or the literal "
            "address. ``value`` is the target to freeze at (integer, "
            "float, or string matching the vt type)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "watch_id or address"},
                "value": {
                    "type": "string",
                    "description": ("value to freeze at (e.g. '9999' or '100.0')"),
                },
                "min_value": {
                    "type": "number",
                    "description": (
                        "optional lower bound; freeze skipped if target would go below this"
                    ),
                },
                "max_value": {
                    "type": "number",
                    "description": (
                        "optional upper bound; freeze skipped if target would go above this"
                    ),
                },
            },
            "required": ["key", "value"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.watch_unfreeze",
        description=(
            "Stop freezing a watched address. The game regains control "
            "of the value. ``key`` may be a watch_id or address."
        ),
        inputSchema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
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
        description="List all currently-active watches, including their freeze status.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="cegm.hex_dump",
        description=(
            "Read a memory region and display it as a hex dump: each row "
            "shows 16 bytes with offset, hex bytes, and printable ASCII. "
            "Use this to examine the memory around a found address — you "
            "can often spot nearby related values (e.g. max HP next to "
            "current HP, or a player name near coordinates).\n\n"
            "Default length is 64 bytes; max is 4096. Address can be "
            "absolute ('0x...') or relative ('module.exe+0x...')."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "hex address to start reading from"},
                "length": {
                    "type": "integer",
                    "default": 64,
                    "minimum": 1,
                    "maximum": 4096,
                    "description": "number of bytes to read",
                },
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
    types.Tool(
        name="cegm.group_create",
        description=(
            "Create a named group of addresses. Groups organize related "
            "values (e.g. 'Player Stats' for HP+MaxHP+Mana). Use groups "
            "to batch freeze/unfreeze and keep the workspace tidy. "
            "The AI should create groups whenever it finds multiple "
            "related addresses.\n\n"
            "Optionally pass initial ``addresses`` (watch_ids or raw "
            "address strings) and a ``note``."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "group name, e.g. 'Player Stats'"},
                "addresses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "optional initial addresses (watch_ids or raw)",
                },
                "note": {"type": "string", "description": "optional description"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.group_add",
        description="Add an address to an existing group.",
        inputSchema={
            "type": "object",
            "properties": {
                "group_id": {"type": "string"},
                "address": {"type": "string"},
            },
            "required": ["group_id", "address"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.group_remove_addr",
        description="Remove an address from a group.",
        inputSchema={
            "type": "object",
            "properties": {
                "group_id": {"type": "string"},
                "address": {"type": "string"},
            },
            "required": ["group_id", "address"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.group_delete",
        description="Delete an entire group (does not remove the watched addresses).",
        inputSchema={
            "type": "object",
            "properties": {"group_id": {"type": "string"}},
            "required": ["group_id"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.group_list",
        description="List all groups with their addresses.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="cegm.group_freeze",
        description=(
            "Freeze all addresses in a group to the same value. "
            "All addresses must already be watched. This is how you "
            "do 'lock all player stats at max' in one call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "group_id": {"type": "string"},
                "value": {"type": "string", "description": "value to freeze all members at"},
            },
            "required": ["group_id", "value"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.group_unfreeze",
        description="Unfreeze all addresses in a group.",
        inputSchema={
            "type": "object",
            "properties": {"group_id": {"type": "string"}},
            "required": ["group_id"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.lua_eval",
        description=(
            "Execute a Lua snippet inside Cheat Engine and return the "
            "result. Use this to test small scripts before creating a "
            "permanent custom tool with cegm.tool_define. Safe: errors "
            "are caught and returned."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Lua code to execute", "minLength": 1},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.find_numeric_stat",
        description=(
            "Guided recipe: find a numeric game value (HP, gold, ammo, etc.) "
            "and optionally freeze it.\n\n"
            "FIRST CALL: pass ``name`` and ``current_value`` (the value "
            "you see on screen right now). Omit current_value for unknown "
            "initial scan. The recipe scans and returns a recipe_id.\n\n"
            "NARROW CALLS: pass ``recipe_id`` + the new ``current_value`` "
            "after the user changes it in-game (e.g. after taking damage). "
            "Repeat until ≤5 candidates remain.\n\n"
            "IDENTIFY: when ≤5 candidates, the recipe auto-adds watches. "
            "Tell the user to change the value in-game and observe which "
            "watch changes. The user tells you 'the first one changed' or "
            "gives you an address.\n\n"
            "CONFIRM: pass ``recipe_id`` + ``confirmed_address`` (the "
            "address that tracked the in-game change) + ``target_value`` "
            "(the value to freeze at, e.g. '9999' for HP). The recipe "
            "freezes it and marks done.\n\n"
            "States: scanning → narrowing → identifying → done."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "human name for the stat: 'HP', 'Gold', 'Ammo'",
                },
                "current_value": {
                    "type": "string",
                    "description": ("current displayed value; omit for unknown-initial scan"),
                },
                "vt": {
                    "type": "string",
                    "default": _VT_DEFAULT,
                    "description": "value type: int32, float, double, int64, byte, etc.",
                },
                "recipe_id": {
                    "type": "string",
                    "description": "returned from previous call; pass to continue the recipe",
                },
                "target_value": {
                    "type": "string",
                    "description": "value to freeze at once confirmed (e.g. '9999')",
                },
                "confirmed_address": {
                    "type": "string",
                    "description": "user-confirmed address (the one that tracked the stat)",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
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
    recipes: RecipeRegistry | None = None,
    groups: GroupRegistry | None = None,
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
                    "Message broadcast to all open dashboard tabs. "
                    "They will auto-submit it. If subscribers is 0, "
                    "tell the user to visit http://127.0.0.1:27077/ "
                    "(or their configured port) in a browser."
                ),
            }
        )

    if name == "cegm.scan":
        if proxy is None or scans is None:
            raise RuntimeError("cegm.scan requires a configured proxy + scan registry")
        value_raw = arguments.get("value")
        value = str(value_raw) if value_raw is not None else ""
        unknown_init = not bool(value)
        vt = str(arguments.get("vt", _VT_DEFAULT))
        max_results = int(arguments.get("max_results", 50))
        protection = str(arguments.get("protection", "+W-C"))
        upstream_type = _vt_to_upstream_type(vt)

        if unknown_init:
            # Unknown initial value scan — capture everything, then narrow
            # with changed/unchanged/increased/decreased.
            scan_args: dict[str, Any] = {"type": "unknown", "protection": protection}
            scan_op = "unknown"
        else:
            scan_args = {"value": value, "type": "exact", "protection": protection}
            scan_op = "exact"

        scan_summary = await _upstream_call(proxy, "scan_all", scan_args)
        count = int(scan_summary.get("count", 0))
        page = await _upstream_call(
            proxy,
            "get_scan_results",
            {"offset": 0, "limit": max_results},
        )
        results = list(page.get("results", []))[:max_results]
        rec = scans.record(
            value=value if value else "(unknown)",
            vt=vt,
            op=scan_op,
            count=count,
            results=results,
            note=f"upstream type={upstream_type} protection={protection}",
        )
        await bus.publish(
            Event.make(
                "scan_started",
                {
                    "scan_id": rec.scan_id,
                    "value": value if value else "(unknown initial)",
                    "vt": vt,
                    "count": count,
                    "page_size": rec.page_size,
                    "unknown_init": unknown_init,
                },
            )
        )
        result: dict[str, Any] = {
            "scan_id": rec.scan_id,
            "value": value if value else "(unknown initial)",
            "vt": vt,
            "count": count,
            "page_size": rec.page_size,
            "results": results,
            "unknown_init": unknown_init,
        }
        if unknown_init:
            result["next_step"] = (
                f"Unknown initial scan captured {count:,} addresses. "
                "Now change the value in-game (take damage, spend money, etc.) "
                "then call cegm.scan_narrow with op='changed'. "
                "Or if you didn't change anything, use op='unchanged'."
            )
        return _text(result)

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

    if name == "cegm.watch_freeze":
        if watches is None:
            raise RuntimeError("cegm.watch_freeze requires a watch registry")
        key = str(arguments.get("key", ""))
        raw_value = arguments.get("value")
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            raise ValueError("'value' is required for freeze")
        min_v = arguments.get("min_value")
        max_v = arguments.get("max_value")
        w = watches.freeze(
            key,
            raw_value,
            min_value=float(min_v) if min_v is not None else None,
            max_value=float(max_v) if max_v is not None else None,
        )
        if w is None:
            raise KeyError(f"no watch found for key={key!r}; add it first with cegm.watch_add")
        await bus.publish(
            Event.make(
                "watch_frozen",
                {
                    "watch_id": w.watch_id,
                    "address": w.address,
                    "vt": w.vt,
                    "label": w.label,
                    "freeze_value": raw_value,
                },
            )
        )
        return _text(
            {
                "ok": True,
                "watch_id": w.watch_id,
                "address": w.address,
                "vt": w.vt,
                "freeze_value": raw_value,
                "note": (
                    f"Address {w.address} frozen at {raw_value}. Broker re-writes every 250ms."
                ),
            }
        )

    if name == "cegm.watch_unfreeze":
        if watches is None:
            raise RuntimeError("cegm.watch_unfreeze requires a watch registry")
        key = str(arguments.get("key", ""))
        if not key:
            raise ValueError("'key' is required")
        w = watches.unfreeze(key)
        if w is None:
            raise KeyError(f"no watch found for key={key!r}")
        await bus.publish(
            Event.make(
                "watch_unfrozen",
                {
                    "watch_id": w.watch_id,
                    "address": w.address,
                    "vt": w.vt,
                    "label": w.label,
                },
            )
        )
        return _text(
            {
                "ok": True,
                "watch_id": w.watch_id,
                "address": w.address,
                "note": "Freeze removed. The game now controls this value again.",
            }
        )

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
                "frozen": w.freeze_value is not None,
                "freeze_value": w.freeze_value,
            }
            for w in watches.list()
        ]
        frozen_count = sum(1 for w in watches.list() if w.freeze_value is not None)
        return _text({"watches": out, "count": len(out), "frozen_count": frozen_count})

    if name == "cegm.group_create":
        if groups is None:
            raise RuntimeError("cegm.group_create requires group registry")
        gname = str(arguments.get("name", ""))
        if not gname:
            raise ValueError("'name' is required")
        addrs = list(arguments.get("addresses") or [])
        note = str(arguments.get("note", ""))
        g = groups.create(gname, [str(a) for a in addrs], note=note)
        await bus.publish(
            Event.make("group_created", {"group_id": g.group_id, "name": g.name, "color": g.color})
        )
        return _text({"ok": True, "group": g.to_dict()})

    if name == "cegm.group_add":
        if groups is None:
            raise RuntimeError("requires group registry")
        gid = str(arguments.get("group_id", ""))
        addr = str(arguments.get("address", ""))
        g = groups.add(gid, addr)
        if g is None:
            raise KeyError(f"group {gid!r} not found")
        return _text({"ok": True, "group": g.to_dict()})

    if name == "cegm.group_remove_addr":
        if groups is None:
            raise RuntimeError("requires group registry")
        gid = str(arguments.get("group_id", ""))
        addr = str(arguments.get("address", ""))
        g = groups.remove_addr(gid, addr)
        if g is None:
            raise KeyError(f"group {gid!r} not found")
        return _text({"ok": True, "group": g.to_dict()})

    if name == "cegm.group_delete":
        if groups is None:
            raise RuntimeError("requires group registry")
        gid = str(arguments.get("group_id", ""))
        # Unfreeze members before deleting the group so no orphaned freezes.
        if watches is not None:
            for addr in groups.addresses_for(gid):
                with contextlib.suppress(Exception):
                    watches.unfreeze(addr)
        ok = groups.delete(gid)
        return _text({"removed": ok})

    if name == "cegm.group_list":
        if groups is None:
            raise RuntimeError("requires group registry")
        return _text({"groups": [g.to_dict() for g in groups.list()], "count": len(groups.list())})

    if name == "cegm.group_freeze":
        if groups is None or watches is None:
            raise RuntimeError("requires groups + watches")
        gid = str(arguments.get("group_id", ""))
        value = arguments.get("value")
        if value is None:
            raise ValueError("'value' is required")
        g = groups.get(gid)
        if g is None:
            raise KeyError(f"group {gid!r} not found")
        frozen = []
        for addr in g.addresses:
            try:
                watches.freeze(addr, value)
                frozen.append(addr)
            except Exception as exc:
                _log.warning("group_freeze.skip", extra={"addr": addr, "err": repr(exc)})
        return _text({"ok": True, "frozen_count": len(frozen), "total": len(g.addresses)})

    if name == "cegm.group_unfreeze":
        if groups is None or watches is None:
            raise RuntimeError("requires groups + watches")
        gid = str(arguments.get("group_id", ""))
        g = groups.get(gid)
        if g is None:
            raise KeyError(f"group {gid!r} not found")
        for addr in g.addresses:
            try:
                watches.unfreeze(addr)
            except Exception as exc:
                _log.warning("group_unfreeze.skip", extra={"addr": addr, "err": repr(exc)})
        return _text({"ok": True})

    if name == "cegm.lua_eval":
        if proxy is None:
            raise RuntimeError("cegm.lua_eval requires a configured proxy")
        code = str(arguments.get("code", ""))
        if not code:
            raise ValueError("'code' is required")
        result = await _upstream_call(proxy, "evaluate_lua", {"code": code})
        return _text({"ok": True, "result": result})

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

    if name == "cegm.find_numeric_stat":
        if proxy is None or scans is None or watches is None or recipes is None:
            raise RuntimeError("cegm.find_numeric_stat requires proxy+scans+watches+recipes")
        stat_name = str(arguments.get("name", "stat"))
        vt = str(arguments.get("vt", _VT_DEFAULT))
        recipe_id = str(arguments.get("recipe_id", ""))
        target_value = str(arguments.get("target_value", ""))
        confirmed = str(arguments.get("confirmed_address", ""))
        value_raw = arguments.get("current_value")
        current_value = str(value_raw) if value_raw is not None else ""

        # ── fresh recipe: first scan ──
        if not recipe_id:
            if current_value:
                scan_args = {
                    "value": current_value,
                    "type": "exact",
                    "protection": "+W-C",
                }
                scan_op = "exact"
            else:
                scan_args = {"type": "unknown", "protection": "+W-C"}
                scan_op = "unknown"

            scan_summary = await _upstream_call(proxy, "scan_all", scan_args)
            count = int(scan_summary.get("count", 0))
            page = await _upstream_call(proxy, "get_scan_results", {"offset": 0, "limit": 10})
            results = list(page.get("results", []))[:10]

            rec = recipes.start(name=stat_name, vt=vt)
            rec = recipes.advance(
                rec.recipe_id,
                state="scanning",
                scan_count=count,
                candidates=results,
            )
            if rec is None:
                raise RuntimeError("recipe disappeared after start")

            scans.record(
                value=current_value if current_value else "(unknown)",
                vt=vt,
                op=scan_op,
                count=count,
                results=results,
            )

            if count == 0:
                msg = (
                    f"No results for '{stat_name}'={current_value if current_value else '?'} "
                    f"with vt={vt}. Try a different value type (float? int64?) or verify "
                    "the value you see on screen matches what you scanned for."
                )
                recipes.advance(rec.recipe_id, state="scanning", message_to_user=msg)
                return _text(
                    {
                        "recipe_id": rec.recipe_id,
                        "state": "scanning",
                        "stat_name": stat_name,
                        "count": 0,
                        "message_to_user": msg,
                    }
                )

            if count <= _MAX_IDENTIFY_CANDIDATES:
                # Already narrow enough — jump to identifying
                watch_ids: list[str] = []
                for r in results:
                    addr = str(r.get("address", ""))
                    w = watches.add(address=addr, vt=vt, label=f"{stat_name}#{len(watch_ids) + 1}")
                    watch_ids.append(w.watch_id)
                recipes.advance(
                    rec.recipe_id,
                    state="identifying",
                    scan_count=count,
                    candidates=results,
                    watch_ids=watch_ids,
                    message_to_user=(
                        f"Found {count} candidate(s) for {stat_name}. "
                        "Watches added. Now change the value in-game and "
                        "tell me which watch changed (e.g. 'the one at 0x...' "
                        "or 'the first/last one'). Then I'll freeze it."
                    ),
                )
                return _text(
                    {
                        "recipe_id": rec.recipe_id,
                        "state": "identifying",
                        "stat_name": stat_name,
                        "count": count,
                        "candidates": results,
                        "watch_ids": watch_ids,
                        "message_to_user": (
                            f"Found {count} candidate(s) for {stat_name}. "
                            "I've added watches. Now change the value in-game "
                            "(take damage, spend gold, etc.) and tell me which "
                            "watch changed. I'll freeze the right one."
                        ),
                    }
                )

            msg = (
                f"Scanned '{stat_name}'={current_value if current_value else '?'}: "
                f"{count} results. Now ask the user to change {stat_name} in the "
                f"game (take damage, spend gold, etc.) and tell you the NEW value. "
                f"Then call this tool again with the same recipe_id and the new value."
            )
            recipes.advance(rec.recipe_id, state="scanning", message_to_user=msg)
            return _text(
                {
                    "recipe_id": rec.recipe_id,
                    "state": "scanning",
                    "stat_name": stat_name,
                    "count": count,
                    "message_to_user": msg,
                }
            )

        # ── continue existing recipe ──
        rec = recipes.get(recipe_id)
        if rec is None:
            raise KeyError(f"recipe {recipe_id!r} not found; it may have expired")

        # ── confirmation: user identified the right address ──
        if confirmed and target_value:
            w = watches.freeze(confirmed, target_value)
            if w is None:
                # Try to add it first, then freeze
                w = watches.add(address=confirmed, vt=vt, label=stat_name)
                w = watches.freeze(w.watch_id, target_value)
            recipes.advance(
                recipe_id,
                state="done",
                confirmed_address=confirmed,
                target_value=target_value,
                message_to_user=(
                    f"{stat_name} at {confirmed} is now frozen at {target_value}. Recipe complete!"
                ),
            )
            return _text(
                {
                    "recipe_id": recipe_id,
                    "state": "done",
                    "stat_name": stat_name,
                    "confirmed_address": confirmed,
                    "frozen_value": target_value,
                    "message_to_user": (
                        f"Done! {stat_name} at {confirmed} is frozen at {target_value}. "
                        "The broker rewrites it every 250ms. "
                        "Use cegm.watch_unfreeze to release it."
                    ),
                }
            )

        # ── identifying state: narrow with new value ──
        if current_value:
            narrow_summary = await _upstream_call(
                proxy, "next_scan", {"type": "exact", "value": current_value}
            )
        else:
            # No value = user triggered changed/unchanged
            narrow_summary = await _upstream_call(proxy, "next_scan", {"type": "changed"})

        count = int(narrow_summary.get("count", 0))
        page = await _upstream_call(proxy, "get_scan_results", {"offset": 0, "limit": 10})
        results = list(page.get("results", []))[:10]

        scans.record(
            value=current_value if current_value else "(changed)",
            vt=vt,
            op="exact" if current_value else "changed",
            count=count,
            results=results,
        )

        if count == 0:
            msg = (
                "Narrowed to 0 results. The value may have changed in an "
                "unexpected way. Try scanning again from scratch with a "
                "different value type (e.g. float instead of int32)."
            )
            recipes.advance(recipe_id, state="scanning", message_to_user=msg)
            return _text(
                {
                    "recipe_id": recipe_id,
                    "state": "scanning",
                    "stat_name": stat_name,
                    "count": 0,
                    "message_to_user": msg,
                }
            )

        if count <= _MAX_IDENTIFY_CANDIDATES:
            watch_ids = []
            for r in results:
                addr = str(r.get("address", ""))
                w = watches.add(address=addr, vt=vt, label=f"{stat_name}#{len(watch_ids) + 1}")
                watch_ids.append(w.watch_id)
            recipes.advance(
                recipe_id,
                state="identifying",
                scan_count=count,
                candidates=results,
                watch_ids=watch_ids,
                message_to_user=(
                    f"Narrowed to {count} candidate(s). Watches added. "
                    "Ask the user to change the value and confirm which "
                    "address tracks it. Then pass confirmed_address + "
                    "target_value to freeze."
                ),
            )
            return _text(
                {
                    "recipe_id": recipe_id,
                    "state": "identifying",
                    "stat_name": stat_name,
                    "count": count,
                    "candidates": results,
                    "watch_ids": watch_ids,
                    "message_to_user": (
                        f"Narrowed to {count} candidate(s) for {stat_name}. "
                        "I've added live watches. Now change the value "
                        "in-game and tell me which watch address changed. "
                        "Then I'll freeze it at your desired value."
                    ),
                }
            )

        msg = (
            f"Narrowed '{stat_name}' to {count} results. Ask the user to "
            f"change the value again and tell you the new {stat_name} value. "
            f"Then call this tool again with recipe_id={recipe_id!r}."
        )
        recipes.advance(
            recipe_id,
            state="narrowing",
            scan_count=count,
            candidates=results,
            message_to_user=msg,
        )
        return _text(
            {
                "recipe_id": recipe_id,
                "state": "narrowing",
                "stat_name": stat_name,
                "count": count,
                "message_to_user": msg,
            }
        )

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
