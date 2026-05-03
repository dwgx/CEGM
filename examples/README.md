# examples/

Reference configurations for connecting MCP clients to a running CEGM broker. The broker listens on `http://127.0.0.1:27077` by default.

## Files

| File | Where it goes | Notes |
|---|---|---|
| [`claude_desktop_config.json`](claude_desktop_config.json) | `%APPDATA%\Claude\claude_desktop_config.json` (Windows) / `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) | Streamable HTTP and stdio variants — pick one |
| [`cursor_mcp.json`](cursor_mcp.json) | `%USERPROFILE%\.cursor\mcp.json` (global) or `<project>/.cursor/mcp.json` (per-project) | HTTP only |
| [`claude_code_mcp_add.txt`](claude_code_mcp_add.txt) | run via `claude mcp add ...` | Both project and local scope shown |
| [`codex_config.toml`](codex_config.toml) | append to `~/.codex/config.toml` | OpenAI Codex CLI |
| [`smoke_test.py`](smoke_test.py) | `python examples/smoke_test.py` | Hit `/api/health` + list tools, no client install needed |

## Workflow

1. Open Cheat Engine — broker auto-starts on 127.0.0.1:27077 (or run `cegm-broker` manually if you haven't installed the plugin yet).
2. Drop the relevant config snippet into your client.
3. Restart the client.
4. Tools named `cegm.*` plus the ~180 from [miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge) become available.
