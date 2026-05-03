# CLAUDE.md — Project Context

This file primes future Claude sessions working in this repository.

## Project: CheatEngineGM (CEGM)

CEGM is a thin **experience layer** built on top of [miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge), vendored as a git submodule under `vendor/`. CE starts → our Lua autorun spawns the broker → broker exposes a single `http://127.0.0.1:27077/` endpoint serving (a) MCP HTTP for external clients (Claude Desktop / Cursor / Claude Code / Codex), (b) a built-in browser dashboard with chat + activity timeline, (c) WebSocket events for live updates.

The differentiating value over the 15+ surveyed competitors is **observability + safety**: live tool-call timeline with diffs, preview-before-commit for destructive writes, snapshots / undo, and a one-click install. The headline architecture decision: see [docs/decisions/0004-build-on-miscusi-peek.md](docs/decisions/0004-build-on-miscusi-peek.md).

## Core architectural decisions (locked)

- **Plugin, not a fork.** Lua autorun bundle in stock CE 7.5+. ADR: [0001](docs/decisions/0001-plugin-vs-fork.md).
- **Python broker.** Auto-spawned from CE. `mcp` 1.27+ (FastMCP in-tree), `starlette`/`uvicorn` for HTTP+WebSocket. Distributed via `uv tool install cegm-broker`. ADR: [0002](docs/decisions/0002-broker-language.md).
- **Vendored upstream.** miscusi-peek/cheatengine-mcp-bridge is a git submodule pinned at a known-good commit. We spawn their `mcp_cheatengine.py` as a stdio child, proxy their tools on our HTTP MCP. We do not fork or modify them; upstream upgrades flow via submodule bump. ADR: [0004](docs/decisions/0004-build-on-miscusi-peek.md).
- **Web UI is the primary observability surface.** Dashboard at `/`, MCP at `/mcp`, WebSocket at `/events`. Phase 5 adds an embedded WebView2 inside CE. Phase 1-4 just opens the user's default browser.
- **Default LLM = DeepSeek**, swappable via OpenAI-compatible `base_url`. Key stored in `%LOCALAPPDATA%\CEGM\config.json`.
- **License: GPL-2.0-only** for CEGM code; vendored miscusi-peek retains its MIT license under `vendor/`. Don't introduce GPL-3.0-only or proprietary deps without a license review.
- **ADR-0003 (file IPC) is superseded.** Old design assumed we'd build the CE bridge from scratch. Now miscusi-peek owns that layer.

## Current phase

Phase 0 (foundation) complete. **Phase 1** is the closed-loop MVP — see [docs/ROADMAP.md](docs/ROADMAP.md).

## Conventions

- **Python (broker):** 3.12+, `uv` for env management. `ruff` for format + lint, `mypy --strict` for types, `pytest` + `pytest-asyncio` + coverage for tests. Package layout `broker/src/cegm_broker/`. Async via `anyio`. Config models via Pydantic v2.
- **Lua (plugin):** targets CE 7.5+ Lua (Lua 5.3-ish + CE extensions). Single autorun entry `plugin/cegm.lua`; submodules under `plugin/lib/`. Bundled `dkjson.lua` (MIT). Don't shell into the broker via `io.popen` waiting for output — `os.execute('start /B ...')` to detach.
- **Web frontend:** vanilla ES2022 modules, Tailwind via CDN (Phase 1; bundle in Phase 5). No build step yet. Pure browser DOM, no SPA framework.
- **Docs:** Markdown, GFM, no emojis. ADRs in `docs/decisions/NNNN-<slug>.md` numbered sequentially. Bilingual sibling files use `.zh-CN.md` suffix (Phase 4).
- **Logs:** structured JSONL with `ts` (ISO-8601 UTC), `level`, `event`, plus event-specific fields. Stderr + file. Stdout is reserved (so we can swap to MCP stdio transport later).
- **CE Lua threading:** miscusi-peek's `ce_mcp_bridge.lua` already handles `createThread`/`synchronize` correctly. Our `cegm.lua` runs strictly main-thread (status form + spawn + port probe — no scans).
- **Encoding:** Process names from `getProcesslist()` and any user-typed strings on non-English Windows go through `ansiToUtf8`/`utf8ToAnsi`. Strings going to broker are always UTF-8.

## Things to read before changing

- New CEGM tool / changing tool surface → update [docs/TOOL_SPEC.md](docs/TOOL_SPEC.md) and the matching `@mcp.tool` in `broker/src/cegm_broker/tools.py`. Don't touch proxied tool names — they come from miscusi-peek.
- New cross-cutting decision → write a new ADR in `docs/decisions/`.
- Bumping the miscusi-peek submodule → run `git submodule update --remote vendor/cheatengine-mcp-bridge`, smoke-test `tools/list` against the new commit, update the pinned-commit reference in ADR-0004.
- CE Lua API doubts → first check [docs/research/ce-lua-api.md](docs/research/ce-lua-api.md). MCP doubts → [docs/research/mcp-python-sdk.md](docs/research/mcp-python-sdk.md). Both are research snapshots from 2026-05-03; cross-check the linked authoritative source before relying.

## Things not to do

- **Don't reimplement miscusi-peek's tools.** Our value is the layer above. If a tool is missing or buggy, file an issue upstream or extend with a `cegm.*`-namespaced wrapper.
- **Don't bind the broker to `0.0.0.0`.** Localhost-only is the security model.
- **Don't `print()` from the broker.** Use the configured `logging` setup. Stray stdout corrupts MCP stdio transport even though our default is HTTP.
- **Don't bundle non-GPL-compatible dependencies** in the broker or plugin. (miscusi-peek/MIT under `vendor/` is fine — preserved as redistributed.)
- **Don't add features for online / multiplayer game cheating.** Project scope is single-player only.
- **Don't add code to `plugin/cegm.lua` that blocks the CE main thread** — no synchronous network calls, no `MemScan:waitTillDone()`, no `sleep`.

## External research conducted

- [docs/research/mcp-python-sdk.md](docs/research/mcp-python-sdk.md) — Python MCP ecosystem snapshot (May 2026). `mcp` 1.27+ (FastMCP merged in-tree), Streamable HTTP transport, scan results as Resources, actions as Tools.
- [docs/research/ce-lua-api.md](docs/research/ce-lua-api.md) — CE 7.5+ Lua API: memory ops, autorun mechanism, custom forms, threading, JSON, .CT format, IPC constraints, distribution norms, gotchas. **Caveat**: my initial sweep missed CE's C plugin SDK; it does exist (`<CE>/plugin/*.dll`, header at `Cheat Engine/plugin/cepluginsdk.h`), and would be required if we ever needed dock-into-main-window UI.
- Competitive landscape on GitHub (15+ active projects); summarized in ADR-0004.
