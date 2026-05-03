# Research: MCP Python Ecosystem (May 2026)

> Captured 2026-05-03. Treat as an input snapshot — re-verify before depending on a specific version pin.

## 1. SDK Options

The canonical Python SDK is **`mcp`** on PyPI, maintained by the Model Context Protocol org. Latest stable is **`mcp 1.27.0`** (April 2026), requires Python 3.10+, MIT licensed. **FastMCP 1.0 was merged into the official SDK in late 2024**, so the bundled high-level API ships in-tree:

- High-level: `from mcp.server.fastmcp import FastMCP`
- Low-level: `from mcp.server.lowlevel import Server`

A **separate, third-party** project — **`fastmcp`** by Jeremiah Lowin / Prefect (latest **3.2.4**, April 2026) — continues independently. It is a superset with extra features (Providers/Transforms architecture from FastMCP 3.0, Feb 2026) but is **not the canonical SDK**. For a new broker, prefer the in-tree `mcp.server.fastmcp` unless you specifically need v3 features.

## 2. Server Transport Modes

| Transport | Use case |
|---|---|
| **stdio** | Local subprocess; client launches the server (Claude Desktop default). Simplest, lowest latency, no port management. |
| **SSE** | **Deprecated** as of 2025-11-25 spec. Don't pick for new work. |
| **Streamable HTTP** | Recommended for production / long-running servers. Single endpoint handles POST + GET; supports multiple concurrent clients; survives restarts. |

**Recommendation for CEGM**: Since the broker is a long-running process that must serve **both** MCP clients and an in-CE chat UI, run **Streamable HTTP on `127.0.0.1:<port>`**. stdio would force the broker to be re-spawned by every MCP client and can't multiplex with the local UI. Use `stateless_http=True, json_response=True` for scalability if needed. Stdio is appropriate only when one MCP client owns the server's lifecycle.

## 3. Tool Definition Pattern

Canonical FastMCP pattern — the function name, docstring, and type hints fully describe the tool:

- Decorator: `@mcp.tool` (no parens needed in current FastMCP; `@mcp.tool()` also valid)
- Types: standard Python annotations (`int`, `str`, `list[str]`, `Literal[...]`, Pydantic models, dataclasses). Use `Annotated[T, Field(description=..., ge=..., le=...)]` for richer metadata.
- **Structured output** (spec 2025-06-18): if your return type is JSON-serializable, FastMCP auto-emits `structuredContent` alongside text. Suppress with `structured_output=False` on the decorator.
- **Streaming**: tools do **not** return streamed payloads. For long jobs, use the `Context` parameter (inject by adding `ctx: Context` to the signature) to call `ctx.report_progress(...)` and `ctx.info(...)` during execution.
- **Errors**: raise `from fastmcp.exceptions import ToolError` (or `from mcp.server.fastmcp.exceptions import ToolError` in the bundled version). `ToolError` messages are always sent to the client even when `mask_error_details=True`; other exceptions are scrubbed to a generic message.

## 4. Resources & Prompts

- **Tool** = LLM-initiated action (`@mcp.tool`). May have side effects.
- **Resource** = client-initiated read-only data, addressed by URI (`@mcp.resource("scan://results/{scan_id}")`). Equivalent to a REST GET. Cheap; the host injects content as context.
- **Prompt** = reusable templated message sequence the user picks via slash command (`@mcp.prompt`).

**For CEGM**: Expose **scan results as a `Resource`** with a URI like `cegm://scan/{scan_id}` — the LLM can read it without burning a tool call when the user asks "what did the last scan find?". Keep `scan_memory`, `read_address`, `write_address`, `pointer_scan`, `attach_process` as **Tools** (they have side effects or are parameterized actions). A **Prompt** like "explain this struct layout" with a `{address}` parameter is also a good fit.

## 5. Client Config Snippets

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json` (Windows) / `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS). Stdio only for local; HTTP is for remote/cloud:

```json
{ "mcpServers": {
  "cegm": { "command": "uvx", "args": ["cegm-broker"], "env": { "CEGM_PORT": "27077" } }
}}
```

**Cursor** — `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global). Same `mcpServers` schema. HTTP variant uses `url`:

```json
{ "mcpServers": {
  "cegm-stdio": { "command": "uvx", "args": ["cegm-broker"] },
  "cegm-http":  { "url": "http://127.0.0.1:27077/mcp" }
}}
```

**Claude Code** — Uses CLI rather than hand-editing. Storage: local-scoped servers go in `~/.claude.json` under that project's path; project-scoped (team-shared) go in `./.mcp.json`. Use:

```bash
claude mcp add --transport http cegm http://127.0.0.1:27077/mcp
claude mcp add --transport stdio cegm -- uvx cegm-broker
```

The resulting `.mcp.json` (project scope) follows the exact same `mcpServers` shape as Claude Desktop / Cursor. Local-scope HTTP entry in `~/.claude.json` looks like `{ "type": "http", "url": "..." }`.

## 6. OpenAI-Compatible LLM Client

Use the **official `openai` Python SDK** with `base_url` overridden — it's the canonical pattern for LM Studio, Ollama, vLLM, OpenRouter, etc. `httpx` raw is only worth it if you want to skip the dependency.

**MCP → OpenAI tool translation** (idiomatic shape):

1. Call the MCP `list_tools` endpoint → get `[{name, description, inputSchema}]`.
2. Map each to OpenAI's format: `{"type":"function","function":{"name":..., "description":..., "parameters": <inputSchema>}}`. The MCP `inputSchema` is already JSON Schema, so this is a 1:1 wrap.
3. On a `tool_calls` response from the model, look up the function name, JSON-parse `arguments`, and forward to `mcp_session.call_tool(name, arguments)`.
4. Append the MCP result back into the chat as a `role: "tool"` message keyed by `tool_call_id`.

The OpenAI Agents SDK does all this for you natively (`MCPServerStreamableHttp`), with optional `mcp_config.convert_schemas_to_strict=True` to enforce strict JSON-schema mode.

## 7. Packaging (Windows-targeted)

Three viable paths, ranked:

1. **`uv tool install` / `uvx` from PyPI** (recommended). uv is 10-100x faster than pip, handles Python version, creates an isolated tool venv. End-user setup: one `uv tool install cegm-broker`. Works great in MCP client configs as `"command": "uvx", "args": ["cegm-broker"]`.
2. **`pipx install`** — same model, ubiquitous, slightly slower.
3. **PyInstaller single-file `.exe`** — only worth it for users who refuse to install Python. Cons: large binary, slower cold-start, AV false positives common on Windows, harder to update.

A plain `pip install` + console-script entry point in `pyproject.toml` (`[project.scripts] cegm-broker = "cegm.broker:main"`) is the foundation all three paths share.

## 8. Logging & Observability

**Hard rule for stdio servers**: stdout is reserved for JSON-RPC frames. Any stray byte (banner, `print()`, ANSI) corrupts the stream and the client disconnects. So:

- **stderr** for log lines; clients (Claude Desktop) capture this into `mcp-server-<name>.log` automatically (Windows: `%APPDATA%\Claude\logs\`).
- Use `logging` with a `StreamHandler(sys.stderr)`, or FastMCP's `get_logger()` which is already wired to stderr.
- Never `print()` without `file=sys.stderr`.

For HTTP transport this is moot (stdout is free), but keep the same discipline so you can swap transports.

**For CEGM**: write structured JSONL log lines to **both** stderr **and** a tailable file (`%LOCALAPPDATA%\CEGM\logs\broker.jsonl`). The Lua plugin can `tail` that file to render a live activity feed inside CE — no extra IPC needed. Log every `tools/call` request + result for the audit pane.

## 9. Reference Open-Source Python MCP Servers

- **modelcontextprotocol/servers** — `https://github.com/modelcontextprotocol/servers`. Official monorepo. Study `src/git` (mcp-server-git) and `src/fetch` for clean low-level Server patterns; `src/filesystem` (Node) for resource-URI design that maps well to scan results.
- **PrefectHQ/fastmcp** — `https://github.com/jlowin/fastmcp`. The third-party FastMCP. README and `examples/` show idiomatic decorator usage, structured output, and `Context` injection patterns.
- **modelcontextprotocol/python-sdk** — `https://github.com/modelcontextprotocol/python-sdk`. Examples directory has minimal stdio + streamable-HTTP servers and a low-level `Server` example, useful when you need to bypass FastMCP for edge cases (custom transport framing, raw JSON-RPC handling for the CE bridge).

Also worth glancing at: `github/github-mcp-server` for production-grade error envelopes, and `wong2/awesome-mcp-servers` as a curated index.

## Sources

- [MCP Python SDK on GitHub](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Python SDK on PyPI (mcp 1.27.0)](https://pypi.org/project/mcp/)
- [FastMCP (third-party) on PyPI](https://pypi.org/project/fastmcp/)
- [FastMCP - Tools docs](https://gofastmcp.com/servers/tools)
- [Anthropic API integration with FastMCP](https://gofastmcp.com/integrations/anthropic)
- [MCP transports specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [Connect to local MCP servers (Claude Desktop)](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
- [Claude Code MCP docs](https://code.claude.com/docs/en/mcp)
- [Cursor MCP docs](https://cursor.com/docs/context/mcp)
- [MCP JSON Configuration on FastMCP](https://gofastmcp.com/integrations/mcp-json-configuration)
- [OpenAI Agents SDK — MCP integration](https://openai.github.io/openai-agents-python/mcp/)
- [Official Example MCP Servers](https://modelcontextprotocol.io/examples)
- [modelcontextprotocol/servers reference repo](https://github.com/modelcontextprotocol/servers)
- [PrefectHQ/fastmcp repo](https://github.com/jlowin/fastmcp)
