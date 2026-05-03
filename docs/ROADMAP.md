# Roadmap

Phases are sequential. Each phase has a binary "done" criterion. No phase ships partially. Updated 2026-05-03 to reflect the [ADR-0004](decisions/0004-build-on-miscusi-peek.md) pivot.

## Phase 0 — Foundation

**Status:** complete (2026-05-03).

- [x] Repo, GPL-2.0 LICENSE, GitHub public repo `dwgx/CEGM`
- [x] Documentation skeleton: README, CLAUDE, ARCHITECTURE, ROADMAP, TOOL_SPEC
- [x] ADRs 0001-0004
- [x] Research snapshots (CE Lua API, MCP Python SDK)
- [x] Vendored `vendor/cheatengine-mcp-bridge` submodule (miscusi-peek, pinned commit)
- [x] Tooling configs (.gitattributes, .editorconfig, ruff, mypy, pytest, CI workflow)
- [x] Scaffolds for `broker/`, `plugin/`, `web/` (no logic yet, just structure + types + entry points)

## Phase 1 — Closed loop MVP

**Goal:** open Cheat Engine → port 27077 is live → external Claude Code or the built-in browser dashboard can list tools, send a chat, and watch a `memory_read` execute end-to-end with the result rendered as a row in the activity feed.

**Done when:**

- `cegm-broker` installable via `uv tool install cegm-broker` (publishable from local sdist for now; PyPI later)
- `cegm.lua` autorun spawns the broker; broker auto-starts, binds 127.0.0.1:27077, exits when CE exits
- Broker spawns `mcp_cheatengine.py` from the vendored submodule and proxies its full tool list on `/mcp` (Streamable HTTP)
- Built-in dashboard at `http://127.0.0.1:27077/` renders: header status, simple chat input, scrollable event timeline
- DeepSeek configured as the default LLM endpoint (user provides API key in dashboard settings); chat round-trips through `/api/chat` and produces tool calls that hit the proxy
- WebSocket `/events` broadcasts every MCP tool invocation and chat token to all open dashboard tabs
- One CEGM-namespaced tool live end-to-end: `cegm.activity_recent` (Resource at `cegm://activity/recent`), so the LLM can read prior context without consuming tool budget
- A `claude_desktop_config.json` example in `examples/` lets a user copy-paste to register CEGM as an MCP server in seconds
- Test coverage: `pytest` ≥ 60% on broker, smoke test that exercises spawn → handshake → list_tools → memory_read against a stub CE
- Demo script in README: open notepad.exe, ask "what's the value at 0x... right now?", watch the read happen in the timeline

## Phase 2 — Differentiation: preview writes + diff visualization

**Goal:** every memory write the LLM proposes can be inspected before it lands; every applied write shows a before/after diff in the activity feed. This is the headline feature versus all surveyed competitors.

**Done when:**

- `cegm.preview_write(address, vt, value)` returns a preview ticket; `cegm.commit_pending(ticket)` applies; `cegm.cancel_pending(ticket)` discards. Pending tickets emit `preview_pending` events the dashboard renders as yellow rows with confirm/discard buttons.
- Settings flag `safety.preview_writes_default` (off by default) routes all proxied `memory_write` calls through the preview pipeline transparently.
- Activity feed renders memory writes with `address | type | before → after`. Bytes-typed writes show a hex-diff. Numeric writes show the delta.
- Confirmed preview event broadcasts; multi-tab dashboards stay in sync.
- Smoke test of the round-trip: dashboard issues a preview, second tab sees the pending row, first tab confirms, second tab sees commit.

## Phase 3 — Differentiation: snapshots + recipes

**Goal:** the user can take a labeled snapshot of all watched addresses, perform a destructive experiment, and roll back with one click. Common workflows ship as parameterized prompts ("recipes") the LLM can run.

**Done when:**

- `cegm.snapshot_take(label?)` / `cegm.snapshot_restore(id)` / `cegm.snapshot_list()` work end-to-end; storage under `%LOCALAPPDATA%\CEGM\snapshots\<session>\<id>.json`
- Dashboard sidebar shows snapshot list with restore and delete actions
- Recipe library: `cegm.recipe_list()` returns built-in recipes; `cegm.recipe_run(name, args)` executes a guided multi-tool sequence. Initial set: `find-numeric-stat`, `follow-pointer-chain`, `dissect-struct-at`. Recipes are MCP `Prompt` definitions internally.
- One-page docs site explaining the safety model

## Phase 4 — Bilingual UX (中英)

**Goal:** dashboard, settings, error messages, and primary docs ship in both Chinese and English. Toggle in settings; default by browser locale.

**Done when:**

- All dashboard strings localized via a single `i18n.json` keyed lookup
- README, ARCHITECTURE, ROADMAP have Chinese versions: `README.zh-CN.md`, `docs/ARCHITECTURE.zh-CN.md`, `docs/ROADMAP.zh-CN.md`
- LLM system prompt selects per-locale tone defaults
- Recipe descriptions and error messages translated

## Phase 5 — Distribution polish

**Goal:** a non-developer Windows user installs CEGM in 60 seconds.

**Done when:**

- `scripts/install.ps1` detects CE install path, copies `cegm.lua` + `ce_mcp_bridge.lua` into `<CE>/autorun/CEGM/`, installs `cegm-broker` via `uv tool install`, drops a desktop shortcut to `http://127.0.0.1:27077/` (CE-must-be-running notice)
- Optional: PyInstaller/Nuitka build of `cegm-broker.exe` for users who refuse to install Python; bundled in the same installer
- Optional: WebView2 embedding of the dashboard inside a CE-side window (replaces the "open browser" button), evaluated via Lazarus' WebView2 binding or a small native helper DLL
- README has install / quickstart / troubleshooting / FAQ
- Tagged `v0.1.0` GitHub release with checksums

## Out of scope (informs design but not built)

- Forking miscusi-peek (we vendor at a pin and follow upstream)
- Online / multiplayer / anti-cheat-evasion features — explicit non-goal
- Linux / macOS support — Windows only at first; CE itself is Windows-primary
- Custom backend implementation that replaces miscusi-peek — would only revisit if upstream stalls
