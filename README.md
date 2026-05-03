# CheatEngineGM (CEGM)

> An LLM-driven Cheat Engine plugin. Talk to Cheat Engine in plain language; the model drives the scanner, reads memory, follows pointer chains, and modifies values — you watch it work.

**Status:** alpha / WIP — no working release yet. See [docs/ROADMAP.md](docs/ROADMAP.md) for the phase plan.

## What it is

CEGM is a Lua plugin for [Cheat Engine](https://github.com/cheat-engine/cheat-engine) plus a small local Python broker that exposes Cheat Engine's scanner as an [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) server. The LLM — your Claude / Cursor / Claude Desktop / any OpenAI-compatible model — sees Cheat Engine's tools and can drive them on your behalf.

You stay in the loop: every tool call the model makes is rendered as a live activity feed inside Cheat Engine. Nothing is hidden. You can pause, override, or take the wheel at any time.

## Why

Manually finding base addresses, offsets, and pointer chains for single-player game memory is repetitive and error-prone. CEGM offloads the grind to a model while keeping you in control.

**Scope:** single-player offline games only. CEGM is not for online or multiplayer titles, and is not designed to evade anti-cheat.

## How it works

```
+------------------+     JSON-RPC over     +-------------------+      MCP / OpenAI tools     +-----------+
|  Cheat Engine    | <===================> |  CEGM broker      | <=========================> |  LLM      |
|  + Lua plugin    |   localhost socket    |  (Python)         |     Streamable HTTP         |  client   |
|  + Activity feed |                       |  - MCP server     |                             |           |
+------------------+                       |  - LLM client     |                             +-----------+
                                           |  - JSONL log tap  |
                                           +-------------------+
```

Two integration paths, same broker:

1. **External MCP client** — point Claude Desktop / Cursor / Claude Code at the broker's `http://127.0.0.1:<port>/mcp` endpoint. Use the model's native chat UI; CE shows what's happening.
2. **In-CE chat panel** — built-in chat UI inside Cheat Engine's plugin window, talking to a user-configured OpenAI-compatible endpoint (DeepSeek, OpenAI, local Ollama, anything).

Both paths land in the same broker, which exposes the same tool surface and writes the same audit log.

## Repository layout

```
plugin/         Lua plugin loaded by Cheat Engine (CE Autorun bundle)
broker/         Python broker — MCP server + LLM client + CE bridge
docs/           Architecture, roadmap, tool spec, ADRs
scripts/        Install / dev helpers
examples/       Client config snippets (Claude Desktop, Cursor, Claude Code)
```

## Install

Not yet available — see [docs/ROADMAP.md](docs/ROADMAP.md). Phase 1 will ship a one-shot installer that copies the plugin to CE's autorun folder and registers the broker as a `uv tool`.

## Build / run from source (developer preview)

Coming once Phase 1 lands. For now the repo is documentation + skeleton only.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — components, dataflow, transport choices
- [Roadmap](docs/ROADMAP.md) — phased delivery plan
- [Tool spec](docs/TOOL_SPEC.md) — what the LLM can call
- [Decisions](docs/decisions/) — architecture decision records (ADRs)

## Contributing

Project is at the skeleton-and-design stage. If you want to help shape it, open an issue describing what you'd build. Code contributions welcome once Phase 1 lands a working scaffold.

## License

CEGM is licensed under [GPL-2.0-only](LICENSE), matching the license of upstream Cheat Engine. CEGM is not affiliated with or endorsed by the Cheat Engine project.
