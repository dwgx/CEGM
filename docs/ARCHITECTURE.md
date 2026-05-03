# Architecture

> Authoritative design as of 2026-05-03. Pivot history: see [ADR-0004](decisions/0004-build-on-miscusi-peek.md). Threading and CE Lua constraints are documented in [research/ce-lua-api.md](research/ce-lua-api.md).

## One-paragraph summary

CEGM is a thin **experience layer** built on top of [miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge), vendored as a git submodule. When Cheat Engine starts, our Lua autorun script spawns `cegm-broker` (Python). The broker spawns miscusi-peek's `mcp_cheatengine.py` as a child stdio MCP server, then exposes a single endpoint at `http://127.0.0.1:27077` serving (a) a Streamable HTTP MCP endpoint at `/mcp` for external clients (Claude Desktop, Cursor, Claude Code, Codex), (b) a built-in web dashboard at `/` for users who don't have or want an external client, and (c) a WebSocket event stream at `/events` that powers a live tool-call timeline with diffs. CEGM adds a small set of safety and observability MCP tools layered over miscusi-peek's ~180-tool surface (`cegm.preview_write`, `cegm.snapshot_*`, `cegm.activity_recent`).

## Process map

```
                                                                        ┌──────────────────────────┐
                                                                        │  Browser (any host)      │
External MCP clients ──────────── HTTP ──────────────────────┐          │  http://127.0.0.1:27077  │
(Claude Desktop / Cursor /                                   │          │  ─────────────────────   │
 Claude Code / Codex / ...)                                  │          │  • Chat UI               │
        │                                                    │          │  • Tool timeline + diff  │
        │  http://127.0.0.1:27077/mcp                        ▼          │  • Settings              │
        │  (Streamable HTTP, JSON-RPC)                                  └────────────┬─────────────┘
        │                                                                            │
        │                                                                            │ WebSocket /events
        ▼                                                                            │ HTTP   /api/*
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  cegm-broker.exe  (Python 3.12+, auto-spawned by CE plugin, dies with CE)           │
│  ───────────────────────────────────────────────────────────────────────────────    │
│  Starlette app on 127.0.0.1:27077:                                                  │
│    /mcp        FastMCP Streamable HTTP — proxies miscusi-peek + adds CEGM tools     │
│    /events     WebSocket — broadcasts tool calls, chat, status                      │
│    /api/chat   POST/SSE — built-in LLM chat (DeepSeek default, OpenAI-compatible)   │
│    /api/config GET/PUT — runtime config (LLM endpoint, key, model)                  │
│    /           Static — index.html + app.js + style.css                             │
│                                                                                     │
│  Internals:                                                                         │
│    • mcp_proxy.py — spawns miscusi-peek's Python child, talks stdio MCP, re-emits   │
│      tool definitions on our /mcp endpoint                                          │
│    • tools.py — CEGM's own MCP tools (preview, snapshot, activity)                  │
│    • llm.py — openai SDK with base_url; tool-call routing into local MCP            │
│    • event_bus.py — fan-out from MCP layer + LLM to all WebSocket clients           │
│    • parent_watch.py — exits broker when CE PID disappears                          │
│    • _logging.py — structured JSONL to file + stderr                                │
└────────────────────────────────────┬────────────────────────────────────────────────┘
                                     │ stdio JSON-RPC (MCP)
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  vendor/cheatengine-mcp-bridge/MCP_Server/mcp_cheatengine.py             │
│  (miscusi-peek's MCP server, MIT, ~180 tools, Python)                    │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │ \\.\pipe\CE_MCP_Bridge_v99
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Cheat Engine 7.5+                                                       │
│  └── autorun/CEGM/                                                       │
│      ├── cegm.lua                  ← our shim                            │
│      │     • status form (broker pid, port, "Open Dashboard" button)     │
│      │     • spawns cegm-broker.exe detached, monitors port              │
│      │     • dies → broker exits via parent_watch                        │
│      └── ce_mcp_bridge.lua         ← copy of miscusi-peek's, vendored    │
│            • exposes CE Lua API to the named pipe                        │
└──────────────────────────────────────────────────────────────────────────┘
```

## Lifecycle

1. **CE starts.** Both autorun scripts run in alphabetical order (`ce_mcp_bridge.lua` then `cegm.lua`).
2. **`ce_mcp_bridge.lua`** opens the server side of `\\.\pipe\CE_MCP_Bridge_v99` and idles waiting for a client.
3. **`cegm.lua`** checks if `127.0.0.1:27077` is already bound. If yes (another CE instance): record "broker shared", show passive status, return. If no: spawn `cegm-broker.exe` detached (`os.execute('start /B "" cegm-broker --port 27077 --parent-pid <PID>')`), then poll the port for readiness up to ~3 s.
4. **`cegm-broker`** binds 27077, starts the Starlette app, spawns `mcp_cheatengine.py` as a stdio child, performs MCP handshake, fetches the tool list, registers them as proxies on its own MCP server, mounts the static dashboard.
5. **External MCP client connects.** Tool calls hit `/mcp` → mcp_proxy forwards to miscusi-peek's stdio child → response comes back. Every step emits an event onto the event bus.
6. **WebSocket clients (dashboard tabs)** receive each event in real time and render the activity feed.
7. **CE exits.** `cegm.lua` is gone with the process. `parent_watch` in the broker sees the CE PID has disappeared (~1 s polling), gracefully shuts down miscusi-peek's child, then exits. Port 27077 is released.

## Web dashboard

The dashboard is a single-page app served from `web/` (top-level repo dir):

- **Chat panel** — textarea + send button. POST to `/api/chat`; server streams the LLM response token-by-token via SSE, plus tool calls happening underneath. Every tool call, every assistant message, every model error is also broadcast on the WebSocket so other tabs stay in sync.
- **Activity timeline** — chronological list of events: `tool_called`, `tool_result`, `chat_user`, `chat_assistant`, `status`. Each tool call expands to show params and result; memory writes show **before/after diff** with addresses + value type. The diff highlight is a CEGM differentiator (no competitor surveyed exposes this).
- **Settings drawer** — LLM endpoint URL, API key, model name, temperature, default scan options. Persisted to `%LOCALAPPDATA%\CEGM\config.json`. Changes reload the LLM client without restarting the broker.

Phase 1 frontend stack: vanilla ES2022 + [Tailwind CDN](https://tailwindcss.com/docs/installation/play-cdn) + native WebSocket. Zero build step. Phase 5 may upgrade to a Vite + Solid.js (or Preact) bundle once feature density justifies it.

## Tool surface

We **proxy** miscusi-peek's ~180 tools verbatim — same names, same schemas. Documented at [their README](https://github.com/miscusi-peek/cheatengine-mcp-bridge#available-tools).

We **add** a small set of CEGM-namespaced tools and resources (full spec in [TOOL_SPEC.md](TOOL_SPEC.md)):

- `cegm.preview_write` — stage a memory write without applying it; broker keeps the pending write in memory and emits a "preview" event for the dashboard. The user (or LLM, prompted by a system message) confirms via `cegm.commit_pending` or discards via `cegm.cancel_pending`.
- `cegm.snapshot_take` / `cegm.snapshot_restore` / `cegm.snapshot_list` — capture the values at all CEGM-watched addresses; restore reverts them in one batch.
- `cegm.activity_recent` (Resource: `cegm://activity/recent?limit=N`) — recent tool calls with diffs, so an LLM can re-read state without burning tool calls.

Every CEGM tool is implemented in our broker; none touch CE directly — they call back into the proxied miscusi-peek tools to read/write memory.

## Concurrency & threading

**Broker side**: single asyncio event loop (`anyio` over asyncio). Concurrency model:

- HTTP/WebSocket served by `uvicorn` workers (single process, async).
- MCP proxy maintains one persistent stdio transport to the miscusi-peek child. Tool calls from MCP HTTP and from the in-dashboard chat both compete for that transport — serialized with an `asyncio.Lock`. Latency budget: tool calls are human-paced, lock contention negligible.
- Event bus is an `asyncio.Queue` per WebSocket client. Producers (mcp_proxy, llm) `put_nowait`; consumers in WebSocket handlers `get`. Dead clients detected on send and dropped.
- Parent-PID watcher runs as a background task, polls `psutil.pid_exists(parent_pid)` every 1 s.

**CE Lua side**: see [research/ce-lua-api.md](research/ce-lua-api.md) §5. miscusi-peek's `ce_mcp_bridge.lua` already handles `createThread` and `synchronize` correctly — we don't add or modify their threading. Our `cegm.lua` only does file-existence checks, port probes, and `os.execute`-style spawn — strictly main-thread, no scans.

## Security model

- Broker binds **`127.0.0.1` only**. Never `0.0.0.0`.
- No authentication on `/mcp` or `/api/*` — `localhost` is the trust boundary. Single-user assumption.
- LLM API keys stored under `%LOCALAPPDATA%\CEGM\config.json` (mode 600 on Windows ACL via `pywin32` if available; plain file otherwise). Never logged. Never shipped to upstream LLM beyond the configured endpoint.
- Mutating tools proxied from miscusi-peek (`memory_write`, `aobwrite`, `lua_exec`, etc.) inherit their existing safety semantics. We add an opt-in **safety mode** (`config.safety.preview_writes_default = true`) that automatically stages every `memory_write` as a preview, requiring an explicit confirmation event from the dashboard before commit. Off by default in v0.1 (matches user expectation of "AI just does it"); on for users who tick the box in settings.
- `vendor/cheatengine-mcp-bridge/`'s license (MIT) is preserved in-tree. CEGM's repo-wide license remains GPL-2.0-only.

## On-disk layout (runtime)

```
%LOCALAPPDATA%\CEGM\
├── config.json                 # user config (LLM endpoint, key, model, theme)
├── logs\
│   └── broker-YYYYMMDD.jsonl   # structured log; rotated daily
├── snapshots\
│   └── <session_id>\
│       └── <snapshot_id>.json  # snapshot data
└── activity\
    └── <session_id>.jsonl      # raw event log per session
```

## On-disk layout (repo)

```
CheatEngineGodMode/
├── plugin/                     CE Lua autorun bundle (our cegm.lua + copied ce_mcp_bridge.lua)
├── broker/                     Python broker (cegm-broker on PyPI)
│   ├── pyproject.toml
│   └── src/cegm_broker/
├── web/                        Static dashboard (HTML / Tailwind / vanilla JS)
├── vendor/
│   └── cheatengine-mcp-bridge/ git submodule (miscusi-peek, MIT)
├── docs/
├── scripts/
└── examples/
```

## Out of scope today

- Single-binary distribution (Phase 5 — PyInstaller / Nuitka)
- Embedded WebView2 inside CE (Phase 5 — replaces the "open browser" button)
- Remote / multi-user broker (security review required first)
- Anti-cheat / online / multiplayer scenarios (explicit non-goal)
