# ADR-0004: Build CEGM on top of miscusi-peek/cheatengine-mcp-bridge as the tool backend, with a web UI as the primary observability surface

- **Status:** accepted
- **Date:** 2026-05-03
- **Supersedes:** [ADR-0003](0003-ipc-mechanism.md) (file-based IPC)
- **Amends:** [ADR-0001](0001-plugin-vs-fork.md), [ADR-0002](0002-broker-language.md) (still valid; this ADR adds the upstream-dependency angle)
- **Deciders:** dwgx (project owner)

## Context

A GitHub survey on 2026-05-03 found 15+ active projects already exposing Cheat Engine to LLMs via MCP, including:

- **[miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge)** (619 ⭐, MIT, last updated 2026-05-03) — the de-facto leader. Hybrid Lua autorun + Python MCP server, named-pipe IPC, ~180 tools covering memory ops, scanning, debugging, code analysis, injection.
- **[cheat-engine/AITools](https://github.com/cheat-engine/AITools)** (21 ⭐, MIT, official Cheat-Engine org) — Lua extension, AIDialog-based UI, but barely maintained (23 commits, no releases).
- **[Eruditi/CE-MCP-Plugin](https://github.com/Eruditi/CE-MCP-Plugin)** (36 ⭐, Chinese) — C plugin DLL, 75 commands over a custom TCP protocol (not standard MCP).
- **[coffeegrind123/cheat-engine-mcp](https://github.com/coffeegrind123/cheat-engine-mcp)** — C++ plugin DLL + Python in Linux container, 176 tools, HTTP/JSON over port 6789.
- 10+ smaller MCP-over-CE implementations.

Common gap across all of them: **no in-CE / in-browser observability layer**. They pipe tool calls headlessly to whatever MCP client the user opens (Claude Desktop / Cursor / Codex), but the user can't watch the tool stream, can't preview destructive writes before they land, can't undo, and can't review the timeline. The original CEGM brief explicitly said: *"用户可以看到 LLM 在做的事情"* — users see what the LLM is doing.

Reimplementing the tool backend (≈180 MCP tools mapping to CE Lua APIs) would duplicate ~6 weeks of miscusi-peek's work. The differentiating value is **everything they don't do**: a transparent UI, a safety layer for writes, a recipe library, a one-click installer, bilingual UX.

## Decision

CEGM is **a thin experience layer** that:

1. **Vendors miscusi-peek as a git submodule** at `vendor/cheatengine-mcp-bridge/` (pinned commit, MIT-licensed; we do not fork it).
2. **Spawns miscusi-peek's `mcp_cheatengine.py` as a child stdio MCP server** and proxies its tools through our own MCP HTTP endpoint. Upstream tool changes flow through automatically by bumping the submodule.
3. **Exposes `http://127.0.0.1:27077/`** as the primary surface:
   - `/mcp` — Streamable HTTP MCP endpoint (proxied tools + CEGM extras). External MCP clients (Claude Desktop, Cursor, Claude Code, Codex) connect here. Zero per-host configuration: as long as CE is running, this URL is live.
   - `/` — a built-in web dashboard (HTML / Tailwind CDN / vanilla ES2022) showing chat, tool-call timeline, diffs, settings.
   - `/events` — WebSocket stream of all activity events.
   - `/api/*` — REST surface for the dashboard's own chat (talks to a configured OpenAI-compatible LLM endpoint, default DeepSeek).
4. **Auto-spawns from CE.** The CE-side autorun script (`plugin/cegm.lua`) launches `cegm-broker` as a detached child process when CE starts. The broker monitors the CE PID and exits when CE exits. Second-CE-instance race is handled by a port-bind probe.
5. **Adds CEGM-only MCP tools and resources** layered over miscusi-peek's surface, documented in [TOOL_SPEC.md](../TOOL_SPEC.md):
   - `cegm.preview_write`, `cegm.commit_pending`, `cegm.cancel_pending` — staged writes
   - `cegm.snapshot_take`, `cegm.snapshot_restore`, `cegm.snapshot_list` — undo / restore points
   - `cegm.activity_recent` (resource at `cegm://activity/recent`) — last N tool calls with diffs
   - Phase 3+: `cegm.recipe_list`, `cegm.recipe_run`

## Consequences

### Positives

- **Eliminates duplicate work.** ~180 tools that already exist, are tested, and are actively maintained upstream.
- **Free upstream upgrades.** Bump submodule = inherit miscusi-peek's improvements.
- **Clear value proposition.** "We are the UI / safety / observability for any CE-MCP backend" — concrete, defensible against the saturated competitor field.
- **Single endpoint for users.** Open CE → port 27077 is up → any MCP client just works. No per-tool installers.
- **Web UI = embeddable.** A single static URL works in any browser today and (Phase 5) inside an embedded WebView2 control inside CE itself.
- **Backend swappability.** Because we proxy at the MCP-stdio layer, we can swap miscusi-peek for `coffeegrind123/cheat-engine-mcp` or a future better backend by changing one config line.

### Negatives

- **Upstream coupling risk.** miscusi-peek could go unmaintained or change their protocol. Mitigation: pinned submodule commit; `vendor/cheatengine-mcp-bridge/` is fully part of our distribution; we can fork at any time without breaking users.
- **Two Lua scripts in `<CE>/autorun/`.** One ours (`cegm.lua`), one theirs (`ce_mcp_bridge.lua`, copied by our installer from the submodule). Slight install complexity; offset by the one-click installer.
- **License-tag obligation.** miscusi-peek is MIT, our project is GPL-2.0-only. We must preserve their `LICENSE` file under `vendor/` and credit them in our `README` and `NOTICE`.
- **Process count.** A user session has: `cheatengine.exe` → `cegm-broker.exe` (Python) → `mcp_cheatengine.py` (Python child) — three processes. Manageable, well within Windows norms, but worth noting for monitoring/diagnostics.
- **GPL/MIT subtle interaction.** Our combined work is GPL-2.0; we redistribute miscusi-peek's MIT-licensed components verbatim with their license intact, which is permitted by both licenses.

### Reversibility

This decision is reversible at three levels:

1. **Different backend** — change which submodule we depend on; keep CEGM's UI/safety layer unchanged.
2. **Fork miscusi-peek** — if their direction diverges from ours, fork the submodule into `dwgx/cheatengine-mcp-bridge` and pin to that.
3. **Fully replace backend with own implementation** — reverts to ADR-0003's file-IPC plan.

## Consequences for prior ADRs

- **ADR-0001 (plugin not fork)** — unchanged. Our CE-side code remains a Lua autorun bundle. C plugin DLL deferred indefinitely (only acquired as a Phase 5+ option for in-CE WebView embedding).
- **ADR-0002 (Python broker)** — unchanged. Python is now mandatory anyway because miscusi-peek requires Python. Our broker stays Python with `uv` distribution.
- **ADR-0003 (file IPC)** — **superseded**. CE↔broker traffic now goes through miscusi-peek's named pipe (`\\.\pipe\CE_MCP_Bridge_v99`) which they already implement. We don't write or read those pipes directly; we just spawn their Python and let it handle CE while we proxy MCP.
