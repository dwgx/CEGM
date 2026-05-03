"""CheatEngineGM broker — MCP HTTP server, browser dashboard, LLM client.

Spawned by Cheat Engine's autorun Lua plugin. Exposes a single
`http://127.0.0.1:<port>/` endpoint serving MCP, the dashboard, and a
WebSocket event stream. Proxies tools from the vendored
`miscusi-peek/cheatengine-mcp-bridge` Python child.
"""

from __future__ import annotations

__version__: str = "0.1.0a1"

__all__ = ["__version__"]
