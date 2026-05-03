"""Spawn and proxy the vendored miscusi-peek MCP server.

CEGM's HTTP MCP endpoint forwards ``tools/list`` and ``tools/call`` to a
child Python process running
``vendor/cheatengine-mcp-bridge/MCP_Server/mcp_cheatengine.py`` over stdio.
This module owns the child's lifecycle and the in-flight request map.

The proxy degrades gracefully: if the child fails to spawn or handshake
(common when Cheat Engine isn't running yet), the broker still starts —
:attr:`MCPProxy.available` becomes ``False``, the tool list reports zero
proxied tools, and the broker's own ``cegm.*`` tools remain usable.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Final, Self

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ConfigDict

from cegm_broker._logging import get_logger

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

_ENV_ENTRY_OVERRIDE: Final[str] = "CEGM_PROXY_ENTRY"
_ENV_PYTHON_OVERRIDE: Final[str] = "CEGM_PROXY_PYTHON"


class ProxyConfig(BaseModel):
    """Inputs the proxy needs to spawn the child."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    python_executable: str = sys.executable
    """Python to run; usually ``sys.executable`` (the broker's own interpreter)."""

    entry_script: Path = _VENDOR_ENTRY
    """Path to ``mcp_cheatengine.py``."""

    handshake_timeout_s: float = 10.0
    """How long to wait for the child to ack ``initialize``."""

    @classmethod
    def from_env(cls) -> Self:
        """Build a config honoring ``CEGM_PROXY_ENTRY`` / ``CEGM_PROXY_PYTHON`` overrides.

        Useful both in tests (point at a non-existent path to skip spawning)
        and for advanced users who want to swap the upstream backend.
        """
        kwargs: dict[str, Any] = {}
        if entry := os.environ.get(_ENV_ENTRY_OVERRIDE):
            kwargs["entry_script"] = Path(entry)
        if py := os.environ.get(_ENV_PYTHON_OVERRIDE):
            kwargs["python_executable"] = py
        return cls(**kwargs)


class MCPProxy:
    """Owner of the miscusi-peek child process and the upstream session.

    Use as an async context manager (or call :meth:`start` and :meth:`stop`
    explicitly). After :meth:`start` returns, :attr:`available` reports
    whether the upstream handshake succeeded; :attr:`tools` carries the
    list of upstream tool definitions (empty if unavailable).
    """

    def __init__(self, config: ProxyConfig | None = None) -> None:
        self._config: ProxyConfig = config or ProxyConfig()
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[types.Tool] = []
        self._available: bool = False
        self._error: str | None = None

    @property
    def available(self) -> bool:
        """``True`` if the child handshake succeeded and tools are usable."""
        return self._available

    @property
    def tools(self) -> list[types.Tool]:
        """Upstream tool definitions, cached at start time. Empty if unavailable."""
        return self._tools

    @property
    def error(self) -> str | None:
        """Last error message from start, if any. ``None`` on success."""
        return self._error

    async def start(self) -> None:
        """Spawn the child and complete the MCP handshake.

        Idempotent: a second call after success is a no-op. On failure the
        proxy is left in an "unavailable" state and any partially-acquired
        resources are released; the broker can keep running.
        """
        if self._available:
            return

        if not self._config.entry_script.is_file():
            self._error = f"entry script missing: {self._config.entry_script}"
            _log.warning("mcp_proxy.entry_missing", extra={"path": str(self._config.entry_script)})
            return

        stack = AsyncExitStack()
        try:
            params = StdioServerParameters(
                command=self._config.python_executable,
                args=[str(self._config.entry_script)],
            )
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(
                session.initialize(),
                timeout=self._config.handshake_timeout_s,
            )
            result = await session.list_tools()

            self._stack = stack
            self._session = session
            self._tools = list(result.tools)
            self._available = True
            self._error = None
            _log.info(
                "mcp_proxy.connected",
                extra={"tool_count": len(self._tools), "entry": str(self._config.entry_script)},
            )
        except Exception as exc:
            self._error = repr(exc)
            self._available = False
            await stack.aclose()
            _log.warning(
                "mcp_proxy.unavailable",
                extra={"err": self._error},
            )

    async def stop(self) -> None:
        """Terminate the child cleanly. Safe to call multiple times."""
        if self._stack is None:
            return
        try:
            await self._stack.aclose()
        finally:
            self._stack = None
            self._session = None
            self._available = False

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        """Forward a ``tools/call`` to the upstream child.

        Raises :class:`RuntimeError` if the proxy isn't available — callers
        should pre-check :attr:`available` for graceful UX.
        """
        if self._session is None or not self._available:
            raise RuntimeError("upstream MCP proxy is not connected")
        return await self._session.call_tool(name, arguments)

    async def __aenter__(self) -> MCPProxy:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.stop()
