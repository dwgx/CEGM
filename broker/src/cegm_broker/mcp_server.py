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

from collections.abc import Sequence

from mcp import types
from mcp.server.lowlevel import Server

from cegm_broker import __version__
from cegm_broker._logging import get_logger
from cegm_broker.event_bus import Event, EventBus
from cegm_broker.mcp_extras import EXTRAS_TOOL_DEFS, is_extra
from cegm_broker.mcp_extras import dispatch as dispatch_extra
from cegm_broker.mcp_proxy import MCPProxy

_log = get_logger(__name__)


def build_server(proxy: MCPProxy, bus: EventBus) -> Server:
    """Construct an MCP :class:`Server` that proxies ``proxy`` and serves CEGM extras.

    The returned server is *not* started; the caller is expected to wrap it
    in a :class:`StreamableHTTPSessionManager` (for HTTP) or hand it to
    ``server.run`` (for stdio).
    """
    # The MCP SDK's ``Server.__init__`` is missing parameter type hints in
    # this release; the call shape is correct but mypy --strict can't verify it.
    server: Server = Server("cegm-broker", version=__version__)

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[types.Tool]:
        # Order: upstream first (familiar to power users), then our extras.
        return [*proxy.tools, *EXTRAS_TOOL_DEFS]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, object]) -> Sequence[types.ContentBlock]:
        await bus.publish(Event.make("tool_called", {"name": name, "arguments": arguments}))
        try:
            if is_extra(name):
                content = await dispatch_extra(name, arguments, bus)
            else:
                if not proxy.available:
                    raise RuntimeError(f"upstream MCP not connected; cannot dispatch {name!r}")
                upstream = await proxy.call_tool(name, dict(arguments))
                content = upstream.content
        except Exception as exc:
            await bus.publish(
                Event.make("tool_error", {"name": name, "error": repr(exc)}),
            )
            raise
        await bus.publish(Event.make("tool_result", {"name": name, "ok": True}))
        return content

    return server
