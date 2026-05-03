"""Spawn and proxy the vendored miscusi-peek MCP server.

CEGM's HTTP MCP endpoint forwards every ``tools/list`` and ``tools/call``
request to a child Python process running
``vendor/cheatengine-mcp-bridge/MCP_Server/mcp_cheatengine.py`` over stdio.
This module owns the child's lifecycle and the in-flight request map.

Phase 1 implementation lands incrementally; this file currently exposes the
stable surface (factories + types) other modules can import without the
spawn machinery being live yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel

from cegm_broker._logging import get_logger

if TYPE_CHECKING:
    pass

_log = get_logger(__name__)

# Resolved at import time so a packaged sdist still finds the vendored path.
# Layout:
#   <repo>/broker/src/cegm_broker/mcp_proxy.py
#   <repo>/vendor/cheatengine-mcp-bridge/MCP_Server/mcp_cheatengine.py
_VENDOR_ENTRY: Final[Path] = (
    Path(__file__).resolve().parents[3]
    / "vendor"
    / "cheatengine-mcp-bridge"
    / "MCP_Server"
    / "mcp_cheatengine.py"
)


class ProxyConfig(BaseModel):
    """Inputs the proxy needs to spawn the child."""

    python_executable: str
    """Python to run; usually ``sys.executable``."""

    entry_script: Path = _VENDOR_ENTRY
    """Path to ``mcp_cheatengine.py``."""

    handshake_timeout_s: float = 10.0
    """How long to wait for the child to ack ``initialize``."""


class MCPProxy:
    """Owner of the miscusi-peek child process and request multiplexing.

    Real implementation lands in Phase 1. The class shell exists now so the
    server module can import ``MCPProxy`` and pass it through ``app.state``.
    """

    def __init__(self, config: ProxyConfig) -> None:
        self._config = config
        self._started: bool = False
        if not config.entry_script.is_file():
            _log.warning(
                "mcp_proxy.entry_missing",
                extra={"path": str(config.entry_script)},
            )

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        """Spawn the child and complete the MCP handshake. NotImplemented in Phase 0."""
        raise NotImplementedError("MCPProxy.start lands in Phase 1")

    async def stop(self) -> None:
        """Terminate the child cleanly. NotImplemented in Phase 0."""
        raise NotImplementedError("MCPProxy.stop lands in Phase 1")
