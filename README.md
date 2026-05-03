# CheatEngineGM (CEGM)

> A live, observable LLM-driven layer over Cheat Engine. Open CE → port `27077` is up → talk to the model from a browser tab or any MCP client (Claude Desktop, Cursor, Claude Code, Codex) → watch tool calls and memory diffs land in real time. Single-player offline use only.

**Status:** alpha / WIP — Phase 1 (closed-loop MVP) in progress. See [docs/ROADMAP.md](docs/ROADMAP.md).

## What it is

CEGM is a thin **experience layer** built on top of the excellent [miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge) (MIT, vendored as a git submodule). When Cheat Engine starts, our Lua autorun spawns a small Python broker that:

- Exposes an **MCP Streamable HTTP** endpoint at `http://127.0.0.1:27077/mcp` so any MCP client (Claude Desktop, Cursor, Claude Code, Codex, …) gets the full tool list with **zero per-host configuration** — as long as CE is running, the URL is live.
- Serves a **built-in browser dashboard** at `http://127.0.0.1:27077/` with chat input, a live tool-call timeline, before/after diffs on memory writes, and a settings drawer for your LLM key.
- Adds a small set of **CEGM-namespaced tools** layered on top: preview-before-commit for writes, named snapshots, restore points, and (Phase 3) a recipe library of common workflows.

The differentiating bet: **observability and safety**. Every surveyed competitor pipes tool calls headlessly to whatever client the user has open. CEGM shows them, lets you preview destructive ones, and lets you roll back.

## Why

Manually finding base addresses, offsets, and pointer chains for single-player game memory is repetitive. CEGM offloads the grind to a model while keeping every step visible and reversible.

**Scope:** single-player offline games only. CEGM is not for online or multiplayer titles, and is not designed to evade anti-cheat.

## How it works

```
                    ┌─ External MCP clients ─────────────┐
                    │  Claude Desktop / Cursor / Codex   │
                    └──────────────┬─────────────────────┘
                                   │ HTTP MCP
                                   ▼                                ┌────────────────────┐
                    ┌──────────────────────────────────────┐        │  Browser           │
                    │  cegm-broker  (Python, autospawned)  │ ◀──── │  http://127.0.0.1: │
                    │  127.0.0.1:27077                     │  WS    │  27077/            │
                    │  /mcp · /events · /api/* · /         │        └────────────────────┘
                    └──────────────┬───────────────────────┘
                                   │ stdio MCP
                                   ▼
                    ┌──────────────────────────────────────┐
                    │  miscusi-peek/cheatengine-mcp-bridge │
                    │  (vendored, MIT, ~180 tools)         │
                    └──────────────┬───────────────────────┘
                                   │ named pipe
                                   ▼
                    ┌──────────────────────────────────────┐
                    │  Cheat Engine 7.5+                   │
                    └──────────────────────────────────────┘
```

Two integration paths, one endpoint:

1. **External MCP client** — point your model client at `http://127.0.0.1:27077/mcp`. Sample configs for Claude Desktop, Cursor, Claude Code in [`examples/`](examples/).
2. **Built-in browser dashboard** — open `http://127.0.0.1:27077/` in any browser. The dashboard talks to its own LLM client (default DeepSeek; pluggable to any OpenAI-compatible endpoint). The same activity timeline shows up regardless of which path drove the tools.

## Repository layout

```
plugin/         CE Lua autorun bundle (our shim + vendored ce_mcp_bridge.lua)
broker/         Python broker — MCP server + LLM client + dashboard backend
web/            Static dashboard (HTML / Tailwind / vanilla JS)
vendor/
  cheatengine-mcp-bridge/   git submodule, miscusi-peek (MIT)
docs/
  ARCHITECTURE.md  ROADMAP.md  TOOL_SPEC.md
  decisions/       ADRs 0001-0004
  research/        external research snapshots
scripts/        installer + dev helpers (Phase 5)
examples/       MCP client config snippets
```

## Install

Not yet released. Phase 1 lands the first usable build. Tracked at [#1](https://github.com/dwgx/CEGM/issues) (TBD). For developers cloning today:

```bash
git clone --recurse-submodules https://github.com/dwgx/CEGM.git
cd CEGM/broker
uv sync
# scaffolding only at this point — no runnable broker yet
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — components, dataflow, lifecycle
- [Roadmap](docs/ROADMAP.md) — phased delivery plan
- [Tool spec](docs/TOOL_SPEC.md) — CEGM extras + proxied tool reference
- [Decisions](docs/decisions/) — ADRs, including [0004](docs/decisions/0004-build-on-miscusi-peek.md) (the headline pivot)

## Acknowledgments

CEGM stands on the shoulders of [miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge), which provides the entire MCP-to-CE tool surface. We vendor their work under `vendor/cheatengine-mcp-bridge/` with their MIT license preserved. If you find CEGM useful, consider starring or sponsoring miscusi-peek's project as well.

## License

CEGM is licensed under [GPL-2.0-only](LICENSE), matching upstream Cheat Engine. Vendored components retain their original licenses (see `vendor/*/LICENSE`). CEGM is not affiliated with or endorsed by the Cheat Engine project or miscusi-peek.
