"""CEGM-namespaced MCP tools and resources layered over the proxied surface.

Every symbol declared here is documented in :doc:`/docs/TOOL_SPEC.md` and
must have a corresponding test in ``tests/test_extras_cegm.py``.

Phase 1 lands ``cegm.activity_recent`` (Resource) plus the
``cegm.preview_*`` triplet. Snapshots arrive in Phase 3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cegm_broker._logging import get_logger

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from cegm_broker.event_bus import EventBus
    from cegm_broker.mcp_proxy import MCPProxy

_log = get_logger(__name__)


def register(mcp: FastMCP, proxy: MCPProxy, bus: EventBus) -> None:
    """Wire CEGM extras onto the given FastMCP server.

    Implementations land in Phase 1 / Phase 3. The signature is stable so
    :mod:`cegm_broker.server` can call this once during lifespan setup.
    """
    del mcp, proxy, bus  # placeholder
    _log.debug("mcp_extras.register_pending")
