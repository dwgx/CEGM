# Architecture

## One-paragraph summary

CEGM is two cooperating processes: a thin Lua plugin loaded into stock Cheat Engine 7.5+, and a Python broker that hosts an MCP Streamable HTTP server, an OpenAI-compatible LLM client, and a JSONL-file bridge to the plugin. External MCP clients (Claude Desktop / Cursor / Claude Code) connect to the broker over HTTP. The broker turns tool calls into JSONL request lines on disk; the plugin tails the file, executes the CE operation on a worker thread, writes a response line back, and emits a UI-visible event to a third JSONL file the user sees as the live activity feed inside Cheat Engine.

## Process map

```
+-----------------------------+        HTTP / MCP        +-----------------------------+
|  External MCP client        | <----------------------> |                             |
|  (Claude Desktop, Cursor,   |   POST /mcp (JSON-RPC)   |                             |
|   Claude Code, ...)         |                          |                             |
+-----------------------------+                          |                             |
                                                         |  CEGM broker (Python)       |
+-----------------------------+        in-process        |  - FastMCP server           |
|  In-CE chat panel (Phase 3) | -----------------------> |  - openai-compat LLM client |
|  (calls own MCP via HTTP)   |                          |  - CE bridge (file IPC)     |
+-----------------------------+                          |  - JSONL logger             |
                                                         |                             |
                                                         |  bind 127.0.0.1:<port>      |
                                                         +-----------------------------+
                                                                  |   ^   |
                                                            append|   |tail
                                                              requests responses
                                                              .jsonl  .jsonl  events.jsonl
                                                                  |   |   |
                                                                  v   |   v
                                                         +-----------------------------+
                                                         |  Cheat Engine 7.5+          |
                                                         |  + autorun/CEGM/cegm.lua    |
                                                         |    - timer poll requests    |
                                                         |    - createThread workers   |
                                                         |    - synchronize() to UI    |
                                                         |    - floating form:         |
                                                         |        status + activity    |
                                                         +-----------------------------+
                                                                  |
                                                                  v
                                                         +-----------------------------+
                                                         |  Target game process        |
                                                         |  (read/write/scan via CE)   |
                                                         +-----------------------------+
```

## Component responsibilities

### Plugin (Lua, in CE)

- **`plugin/cegm.lua`** — autorun entry. Adjusts `package.path`, requires modules, creates the floating form, registers a global `createTimer` for the IPC poll. Chains `onOpenProcess` rather than overwriting it (research §9 gotcha).
- **`plugin/lib/bridge.lua`** — opens `requests.jsonl` for read, seeks to the saved offset, parses any new lines into request objects. Appends response objects to `responses.jsonl` with atomic small writes (one line ≤ 4 KiB; oversize payloads go to side-files referenced by URI).
- **`plugin/lib/workers.lua`** — wraps `createThread` for blocking CE operations (scans, AOB, big reads). Uses `synchronize(fn)` for any operation that touches CE forms, `AddressList`, or returns to the main thread.
- **`plugin/lib/tools.lua`** — implements the handlers the broker can request. Each handler maps to a CE Lua API call documented in [research/ce-lua-api.md](research/ce-lua-api.md).
- **`plugin/lib/ui.lua`** — floating form (LCL, no native dock support). Status bar (broker connected? attached process? scan in flight?) plus a tail of `events.jsonl` rendered as a scrollback. Writes a per-control color theme (research §3 — no built-in dark mode).
- **`plugin/lib/log.lua`** — parses one JSONL event into a UI row.
- **`plugin/lib/dkjson.lua`** — vendored pure-Lua JSON (MIT). No DLL, no compile step.

### Broker (Python)

- **`server.py`** — instantiates `FastMCP("cegm")`, mounts tools/resources/prompts, runs Streamable HTTP on `127.0.0.1:$CEGM_PORT` (default 27077). `stateless_http=True, json_response=True` for simplicity.
- **`tools.py`** — `@mcp.tool` definitions. Each tool validates inputs, hands off to `ce_bridge.call(method, params)`, awaits the response, and either returns a structured payload or raises `ToolError`.
- **`resources.py`** — `@mcp.resource("cegm://scan/{scan_id}")` exposes the last scan's results so an LLM can re-read state without burning a tool call (research §4). `cegm://modules/{pid}` exposes the loaded-module map.
- **`prompts.py`** — `@mcp.prompt` templates: `find-numeric-stat`, `follow-pointer-chain`, `dissect-struct-at`. Phase 4.
- **`ce_bridge.py`** — manages the JSONL files. Appends a request line tagged with a UUID `id`, registers a future, watches `responses.jsonl` (via `watchdog`'s `ReadDirectoryChangesW` on Windows; falls back to polling), resolves the future when a matching `id` arrives.
- **`llm.py`** — wraps `openai.OpenAI(base_url=...)` with the user's configured endpoint. Handles tool-call routing into the local MCP session for the in-CE chat panel.
- **`log.py`** — `logging` setup that writes the same record to stderr (terminal) and `events.jsonl` (CE feed). Strict no-`print` policy.
- **`config.py`** — loads `%LOCALAPPDATA%\CEGM\config.json`. Schema in [docs/CONFIG.md](CONFIG.md) (Phase 1).
- **`cli.py`** — `cegm-broker` console-script entry: `--port`, `--rpc-dir`, `--log-level`, `--print-mcp-config`.

## Dataflow: a single tool call (from external MCP client)

1. MCP client sends `tools/call { name: "scan_first", arguments: {...} }` to `http://127.0.0.1:27077/mcp`.
2. FastMCP dispatches to `tools.scan_first(...)`.
3. Tool validates args, calls `ce_bridge.call("scan_first", {...}) -> Future`.
4. Bridge writes `{"id": "u-1", "kind": "request", "method": "scan_first", "params": {...}, "ts": "..."}` to `requests.jsonl`. Logs an `event` line to `events.jsonl`: `{"kind": "event", "event": "tool_dispatched", ...}`.
5. CE plugin's timer wakes; `bridge.lua` reads new line, dispatches into a `createThread` worker.
6. Worker calls `tools.lua` → `MemScan:firstScan(...)`, waits for it (off-main-thread), produces a `FoundList`, slices it (`.Count`, indexed), serializes top-N hits to JSON.
7. Worker `synchronize(fn)` writes `{"id":"u-1","kind":"response","result":{...}}` to `responses.jsonl` and emits an `event` line: `{"kind":"event","event":"tool_completed","duration_ms":1234, ...}`.
8. Broker `watchdog` fires, parses the line, resolves the matching future.
9. FastMCP returns the result to the MCP client.
10. CE plugin's UI tails `events.jsonl` and renders both events as activity-feed rows.

The full timeline is visible to the user without any extra plumbing.

## Dataflow: in-CE chat (Phase 3)

Same diagram, but step 1 is replaced by the in-CE chat panel acting as an MCP client against the same `127.0.0.1:27077/mcp` endpoint. The broker's `llm.py` handles the LLM round-trip: take user message → list_tools → forward to OpenAI-compatible endpoint → receive `tool_calls` → invoke tools (which loop back into our same `tools.py`) → return final assistant message. The in-CE panel shows streaming tokens; the activity feed (events.jsonl) shows tool calls. Single source of truth.

## Threading and concurrency

**CE side**:

- One `createTimer` on the main thread, ~50–100 ms interval. On each tick: drain new lines from `requests.jsonl`; spawn a `createThread` per request.
- Each worker has shared Lua state with the main thread, so:
  - All CE operations (`MemScan`, `readBytes`, `getAddressList()`, etc.) run inside the worker.
  - All form / `AddressList` mutation is wrapped in `synchronize(fn)` to push onto the main thread.
  - File appends use `synchronize` only when concurrency-sensitive (we serialize file writes via a queue to avoid interleaving).
- Workers are short-lived (one tool call each). For long-running scans we plan to add cancellable workers in Phase 2 — store the worker handle on `bridge.lua` keyed by request id, expose a `cancel_request` tool.

**Broker side**:

- FastMCP runs on `asyncio`. Each tool invocation is `async def`, awaits a `Future` resolved when the matching response arrives.
- File watching: a single `watchdog.Observer` posts new `responses.jsonl` lines onto an `asyncio.Queue`; a consumer task drains and resolves futures.
- File writes are serialized through an `asyncio.Lock` to keep JSONL atomic on Windows where append `O_APPEND` semantics are weaker than POSIX.

## Bridge protocol (JSON-RPC over JSONL)

Every line is one JSON object. Reserved fields:

```jsonc
{
  "id": "u-1",                  // UUIDv4 string, request/response correlation
  "kind": "request",            // "request" | "response" | "event" | "hello"
  "ts": "2026-05-03T14:22:00Z", // ISO-8601 UTC, broker-side wall clock
  "v": 1                        // protocol version
}
```

Request adds `method` (string, snake_case tool name) and `params` (object).
Response adds `result` (any) on success or `error: {code, message, data?}` on failure.
Event adds `event` (string label) and `data` (object) — purely advisory, no request/response correlation.

A `hello` line is exchanged at startup so both sides verify version compatibility before processing requests. Mismatched `v` aborts the bridge with a fatal log line.

## File layout on disk (runtime)

```
%LOCALAPPDATA%\CEGM\
├── config.json                  # user settings (LLM endpoint, model, port, theme)
└── rpc\
    └── <session_id>\            # one dir per broker run; UUID
        ├── requests.jsonl       # broker -> plugin
        ├── responses.jsonl      # plugin -> broker
        ├── events.jsonl         # broker activity log; plugin tails for feed
        └── payloads\            # oversize blobs referenced by URI
            └── <id>.bin
```

A simple TTL sweeper deletes `<session_id>` directories older than 24 h on broker start.

## Security model (single-user localhost only)

- Broker binds **`127.0.0.1` only**. Never `0.0.0.0`. No remote access path.
- No authentication on the MCP endpoint — the security boundary is `localhost`. Adding HMAC tokens between broker and plugin is a Phase 5 hardening item but not MVP.
- LLM API keys live in `%LOCALAPPDATA%\CEGM\config.json`, never committed, never logged.
- Tool calls that mutate process memory (`memory_write`, `address_freeze`, `lua_exec`) are gated by an opt-in setting per tool. The user's first use of a mutating tool prompts confirmation in the CE panel.
- `lua_exec` (arbitrary CE Lua) is off by default; enabling it requires editing `config.json`. It is the obvious foot-gun.

## Out-of-scope today (informs design but not built)

- Remote / multi-user broker (binding non-localhost) — security review required first.
- Anti-cheat or online-game scenarios — explicit non-goal.
- Auto-update — manual reinstall for now.
- Packaging into a single binary — `uv tool install` is the v0 path.
