"""Build the low-level MCP :class:`~mcp.server.lowlevel.Server` for our HTTP endpoint.

We use the low-level ``Server`` rather than ``FastMCP`` so we can register
upstream-proxied tools dynamically (their definitions only become known
after the child handshake). FastMCP's ``add_tool`` requires statically-
shaped Python functions, which is awkward for arbitrary tool schemas.

The single ``Server`` instance is wrapped by a
:class:`~mcp.server.streamable_http_manager.StreamableHTTPSessionManager`
in :mod:`cegm_broker.server`, then mounted into the Starlette app at
``/mcp``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server

from cegm_broker import __version__
from cegm_broker._logging import get_logger
from cegm_broker.dynamic_tools import DynamicToolRegistry
from cegm_broker.event_bus import Event, EventBus
from cegm_broker.groups import GroupRegistry
from cegm_broker.mcp_extras import EXTRAS_TOOL_DEFS, is_extra
from cegm_broker.mcp_extras import dispatch as dispatch_extra
from cegm_broker.mcp_proxy import MCPProxy
from cegm_broker.recipes import RecipeRegistry
from cegm_broker.scans import ScanRegistry
from cegm_broker.watches import WatchRegistry

_log = get_logger(__name__)

# ── tool categorization ─────────────────────────────────────────────────
# Maps upstream tool names to a category. Uncategorized tools get "utility".
# Regex patterns match families of tools (e.g. "write_*").

_CATEGORY_RULES: list[tuple[str, str]] = [
    ("^(open_process|get_process_list|get_process_info|close_process)$", "process"),
    (
        "^(read_memory|read_integer|read_float|read_double|read_string|"
        "read_bytes|read_pointer|read_pointer_chain|read_memory_region|"
        "read_int8|read_int16|read_int32|read_int64|read_uint32|"
        "read_address|get_value_at)$",
        "memory_read",
    ),
    (
        "^(write_integer|write_float|write_double|write_string|write_bytes|"
        "write_memory|write_int8|write_int16|write_int32|write_int64|"
        "write_uint32|aobwrite|memory_write|set_value_at)$",
        "memory_write",
    ),
    (
        "^(scan_all|next_scan|get_scan_results|new_scan|reset_scan|"
        "scan_alignment|create_memscan|memscan_.*)$",
        "scan",
    ),
    ("^(aob_scan|aob_scan_unique|aob_scan_region|aob_scan_module|aob_.*)$", "aob"),
    (
        "^(find_pointer_path|find_pointer|resolve_pointer|"
        "read_pointer_chain|follow_pointer|pointer_.*)$",
        "pointer",
    ),
    (
        "^(disassemble|disassemble_at|get_instruction|get_instruction_at|"
        "get_mnemonic|instruction_.*)$",
        "disasm",
    ),
    (
        "^(set_breakpoint|remove_breakpoint|list_breakpoints|"
        "enable_breakpoint|disable_breakpoint|breakpoint_.*|"
        "hw_breakpoint.*|dbvm_.*)$",
        "breakpoint",
    ),
    (
        "^(auto_assembl|auto_assembler|inject_dll|evaluate_lua|"
        "lua_exec|create_thread|load_library)$",
        "inject",
    ),
    (
        "^(save_cheat_table|load_cheat_table|export_cheat_table|cheat_table_.*)$",
        "cheat_table",
    ),
    ("^(get_symbol|lookup_symbol|symbol_.*|module_.*|get_module)$", "symbol"),
    ("^(freeze|unfreeze|freeze_address|freeze_.*)$", "freeze"),
]


def _categorize_tool_name(name: str) -> str:
    """Return a category slug for an upstream tool name."""
    for pattern, category in _CATEGORY_RULES:
        if re.match(pattern, name, re.IGNORECASE):
            return category
    return "utility"


def _enrich_tool_description(tool: types.Tool) -> types.Tool:
    """Inject a category tag into a proxied tool's description."""
    cat = _categorize_tool_name(tool.name)
    prefix = f"[{cat}] "
    desc = tool.description or ""
    if not desc.startswith("["):
        return types.Tool(
            name=tool.name,
            description=prefix + desc,
            inputSchema=tool.inputSchema,
        )
    return tool


def build_server(
    proxy: MCPProxy,
    bus: EventBus,
    *,
    scans: ScanRegistry,
    watches: WatchRegistry,
    recipes: RecipeRegistry,
    groups: GroupRegistry,
    dynamic: DynamicToolRegistry,
) -> Server:
    """Construct an MCP :class:`Server` that proxies ``proxy`` and serves CEGM extras."""
    # The MCP SDK's ``Server.__init__`` is missing parameter type hints in
    # this release; the call shape is correct but mypy --strict can't verify it.
    server: Server = Server("cegm-broker", version=__version__)

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[types.Tool]:
        # Upstream first (with category tags injected), then static
        # CEGM extras, then any user-defined custom.* tools.
        enriched_upstream = [_enrich_tool_description(t) for t in proxy.tools]
        return [*enriched_upstream, *EXTRAS_TOOL_DEFS, *dynamic.mcp_tools()]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(
        name: str, arguments: dict[str, Any]
    ) -> Sequence[types.ContentBlock] | types.CallToolResult:
        """Dispatch a single ``tools/call`` to either a CEGM extra or upstream."""
        await bus.publish(Event.make("tool_called", {"name": name, "arguments": arguments}))
        try:
            if is_extra(name):
                result: Sequence[types.ContentBlock] | types.CallToolResult = await dispatch_extra(
                    name,
                    arguments,
                    bus=bus,
                    proxy=proxy,
                    scans=scans,
                    watches=watches,
                    recipes=recipes,
                    groups=groups,
                    dynamic=dynamic,
                )
            else:
                if not proxy.available:
                    raise RuntimeError(f"upstream MCP not connected; cannot dispatch {name!r}")
                result = await proxy.call_tool(name, dict(arguments))
        except Exception as exc:
            await bus.publish(
                Event.make("tool_error", {"name": name, "error": repr(exc)}),
            )
            raise
        await bus.publish(Event.make("tool_result", {"name": name, "ok": True}))
        return result

    return server
