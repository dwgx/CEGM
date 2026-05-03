# CLAUDE.md — Project Context

This file primes future Claude sessions working in this repository.

## Project: CheatEngineGM (CEGM)

LLM-driven plugin for Cheat Engine. The user wants to chat with an AI that can autonomously drive CE's scanner to find game memory addresses, follow pointer chains, and modify values — with every action surfaced in a live UI inside CE.

## Core architectural decisions (locked)

- **Plugin, not a fork.** Lua plugin loaded into stock Cheat Engine 7.5+. Avoids GPL distribution friction and tracks upstream automatically. ADR: [docs/decisions/0001-plugin-vs-fork.md](docs/decisions/0001-plugin-vs-fork.md).
- **Two-process design.** CE Lua plugin (thin: UI + tool execution) ↔ Python broker (MCP server + LLM client + bridge). Separated because CE Lua's main-thread model can't safely host an HTTP server, and Python has the mature MCP/LLM ecosystem. ADR: [docs/decisions/0002-broker-language.md](docs/decisions/0002-broker-language.md).
- **MCP-first surface.** Broker exposes tools via MCP Streamable HTTP on `127.0.0.1`. External clients (Claude Desktop / Cursor / Claude Code) connect at `http://127.0.0.1:<port>/mcp`. The optional in-CE chat panel is just another MCP client pointed at the same endpoint.
- **File-based IPC for the CE↔broker bridge.** JSONL files under `%LOCALAPPDATA%/CEGM/rpc/` for `requests` (broker→plugin), `responses` (plugin→broker), and `events` (broker→plugin audit feed). Chosen because CE Lua has no bundled sockets and shipping a custom DLL doubles the build matrix. ADR: [docs/decisions/0003-ipc-mechanism.md](docs/decisions/0003-ipc-mechanism.md).
- **JSONL audit log is the activity feed.** Broker writes structured JSONL events (one of which doubles as the IPC channel above). CE plugin tails `events.jsonl` and renders the stream — no extra IPC channel needed for UX.
- **License is GPL-2.0-only.** The whole repo. Matches upstream CE; no compatibility ambiguity. Don't introduce dependencies that are GPL-3.0-only or proprietary without a license review.

## Current phase

Phase 0 — repo scaffold and design docs only. No working code yet. Phase 1 (MVP) is the next milestone; see [docs/ROADMAP.md](docs/ROADMAP.md).

## Conventions

- Docs: Markdown, GFM, no emojis. ADRs go in `docs/decisions/NNNN-<slug>.md` numbered sequentially.
- Python (broker): Python 3.11+, `uv` for env management, `ruff` lint + format, `pytest` tests, type-hinted. Package layout `broker/src/cegm_broker/`.
- Lua (plugin): targets the Lua runtime that ships with CE 7.5 (Lua 5.3-ish; some CE-specific extensions). Single autorun entry `plugin/cegm.lua`; submodules under `plugin/lib/`.
- Logs: structured JSONL with `ts` (ISO-8601 UTC), `level`, `event`, plus event-specific fields. Never `print()` to stdout from broker code (stdout is reserved for stdio MCP transport even though we default to HTTP).
- CE Lua threading: scans must run inside `createThread`; UI mutation must be inside `synchronize(fn)`. Don't call `MemScan:waitTillDone()`, `AOBScan` on full address space, or `sleep` from the main thread. `createMemScan(progressbar)` requires a non-nil progressbar arg in some builds — pass one even if hidden.
- Encoding: Process names from `getProcesslist()` and any user-typed strings on non-English Windows go through `ansiToUtf8`/`utf8ToAnsi`. Strings going to broker are always UTF-8.

## Things to read before changing

- New tool / changing tool surface → update [docs/TOOL_SPEC.md](docs/TOOL_SPEC.md) and the matching `@mcp.tool` in `broker/src/cegm_broker/tools.py`.
- New cross-cutting decision → write a new ADR in `docs/decisions/`.
- Bridge protocol changes → both sides (`plugin/lib/bridge.lua` and `broker/src/cegm_broker/ce_bridge.py`) must move together; bump the version field in the handshake message.
- CE Lua API doubts → first check [docs/research/ce-lua-api.md](docs/research/ce-lua-api.md). MCP doubts → [docs/research/mcp-python-sdk.md](docs/research/mcp-python-sdk.md). Both are research snapshots from 2026-05-03; cross-check the linked authoritative source before relying.

## Things not to do

- Don't add code to `plugin/cegm.lua` that blocks the CE main thread (no synchronous network calls). Use `createTimer` for polling and the bridge socket for any LLM-side work.
- Don't `print()` from the broker — use the configured `logging` setup. Stray stdout corrupts MCP stdio transport if a user later switches to it.
- Don't bundle non-GPL-compatible dependencies.
- Don't add features for online / multiplayer game cheating. Project scope is single-player only.

## External research conducted

- [docs/research/mcp-python-sdk.md](docs/research/mcp-python-sdk.md) — Python MCP ecosystem snapshot (May 2026). Use `mcp` 1.27+ (FastMCP merged in-tree), Streamable HTTP transport, scan results as Resources, actions as Tools.
- [docs/research/ce-lua-api.md](docs/research/ce-lua-api.md) — CE 7.5+ Lua API: memory ops, autorun mechanism, custom forms, threading, JSON, .CT format, IPC constraints, distribution norms, gotchas.
