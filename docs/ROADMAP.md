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

## Phase 2 — RE workbench: scan / watch / hex / tool browser

**Goal:** turn the dashboard from "JSON-blob log" into a workbench that mirrors the operations a real reverse engineer performs. See [RE_WORKBENCH_PLAN.md](RE_WORKBENCH_PLAN.md) for the friction log and feature spec.

**Done when:**

- `cegm.scan` / `cegm.scan_narrow` / `cegm.scan_drop` — one-shot scan with inline first page; right-rail "Scans" tab renders results, supports per-row narrow / watch / write actions
- `cegm.watch_add` / `watch_remove` / `watch_list` + asyncio polling task — `watch_update` events on the WebSocket; "Watches" tab renders a live-updating grid
- `cegm.hex_dump` — inline hex+ASCII viewer, opens from any row that has an address
- Tool browser tab — categorized search over the 175 upstream tools (`process` / `memory` / `scan` / `pointer` / `disasm` / `breakpoint` / `inject` / `cheat_table` / `cegm`), populated by `_meta.category` tags the proxy adds at registration time

## Phase 3 — Disassembly + recipes

- `cegm.disasm_at` returning structured rows; syntax-highlighted disasm pane
- Pointer-chain visualizer (boxes per level, live values)
- `cegm.recipe_list` / `recipe_run` + built-in recipes: `find_numeric_stat`, `follow_pointer_chain`, `find_what_writes`, `code_cave_inject`, `aob_signature_lock`
- MCP `Prompt` definitions matching each recipe

## Phase 4 — Diff + preview-write + snapshots

(Was Phase 2 in the original plan; demoted because the items above turn out to give a much bigger UX lift first.)

**Goal:** every memory write the LLM proposes can be inspected before it lands; every applied write shows a before/after diff in the activity feed.

**Done when:**

- `cegm.preview_write(address, vt, value)` returns a preview ticket; `cegm.commit_pending(ticket)` applies; `cegm.cancel_pending(ticket)` discards. Pending tickets emit `preview_pending` events the dashboard renders as yellow rows with confirm/discard buttons.
- Settings flag `safety.preview_writes_default` (off by default) routes all proxied `memory_write` calls through the preview pipeline transparently.
- Activity feed renders memory writes with `address | type | before → after`. Bytes-typed writes show a hex-diff. Numeric writes show the delta.
- `cegm.snapshot_take(label?)` / `cegm.snapshot_restore(id)` / `cegm.snapshot_list()` work end-to-end.
- Dashboard sidebar shows snapshot list with restore actions.

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
