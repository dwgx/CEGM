# examples/

Reference configurations for connecting MCP clients to a running CEGM broker. The broker listens on `http://127.0.0.1:27077` by default.

## Planned (Phase 1)

- `claude_desktop_config.json` — drops in at `%APPDATA%\Claude\claude_desktop_config.json` (Windows). Streamable HTTP variant.
- `cursor_mcp.json` — drops in at `%USERPROFILE%\.cursor\mcp.json` (global) or `<project>\.cursor\mcp.json`.
- `claude_code_mcp_add.txt` — the exact `claude mcp add --transport http cegm http://127.0.0.1:27077/mcp` invocation.
- `codex_config.toml` — Codex CLI MCP server snippet.
- `openai_chat_smoke.py` — minimal OpenAI-compatible client smoke test against `/api/chat`.

## Status

Empty — placeholders only. See [docs/ROADMAP.md](../docs/ROADMAP.md) Phase 1.
