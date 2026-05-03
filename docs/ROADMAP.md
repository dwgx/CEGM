# Roadmap

Phases are sequential. Each phase has a binary "done" criterion — either it works end-to-end or it doesn't. No phase ships partially.

## Phase 0 — Foundation (this commit)

**Goal:** repo, license, design docs, ADRs, directory skeleton on GitHub.

**Done when:**
- [x] Git repo initialized, GPL-2.0 LICENSE in place
- [x] README, CLAUDE.md, ARCHITECTURE.md, ROADMAP.md, TOOL_SPEC.md committed
- [x] ADR-0001 (plugin vs fork) and ADR-0002 (broker language) committed
- [x] `plugin/`, `broker/`, `docs/`, `scripts/`, `examples/` skeletons exist
- [x] `dwgx/CEGM` repo created on GitHub, `main` branch pushed

## Phase 1 — MVP "hello, scan"

**Goal:** end-to-end loop: external Claude/Cursor sends a chat → MCP tool fires → CE Lua plugin executes a scan → result returned to LLM → user sees the tool call in the CE activity feed.

**Done when:**
- Broker installs via `uv tool install cegm-broker` and runs MCP Streamable HTTP on a configurable localhost port
- CE Lua plugin auto-loads from `<CE>/autorun/CEGM/`, opens a docked panel with two regions: "activity feed" (tail of broker JSONL) and a "status" line (broker connection + attached process)
- 5 tools work end-to-end via Claude Desktop: `process_attach`, `process_list`, `scan_first`, `scan_results`, `memory_read`
- A second cheat-table-affecting tool, `address_freeze`, is verified to add a row to CE's address list
- Bridge protocol versioned and documented; mismatched versions refuse to handshake

**Demo script:**
> Open notepad.exe, type a number, attach via the chat ("attach to notepad"), `scan_first` for that number as int32, retype to a different number, `scan_next` filtering to changed values, `memory_read` the surviving address, `memory_write` to set it back. CE activity feed shows every step.

## Phase 2 — Tool surface complete

**Goal:** the LLM has every primitive it needs to do a real reverse-engineering session.

**Done when:**
- `scan_next` with all comparison modes (exact / changed / unchanged / increased / decreased / between)
- `pointer_scan` returns N candidate pointer paths within a budget (rmax depth, max addresses)
- `aob_scan` (array-of-bytes pattern with wildcards), returns hits and disassembly context
- `memory_write` covers byte / int16 / int32 / int64 / float / double / string / aob
- `lua_exec` escape hatch for one-off CE Lua, gated by an opt-in setting (it's a foot-gun)
- Cheat table I/O: `cheat_table_save`, `cheat_table_load`
- All tools have schemas in [TOOL_SPEC.md](TOOL_SPEC.md), test fixtures in `broker/tests/`

## Phase 3 — In-CE chat panel

**Goal:** the user does not need a separate Claude Desktop window. The CE plugin window contains a working chat against any OpenAI-compatible endpoint.

**Done when:**
- Plugin panel adds a "Chat" tab with input box + streamed assistant output
- User configures endpoint URL + API key + model in a settings dialog (persisted under `%LOCALAPPDATA%/CEGM/config.json`)
- Tool calls from the in-CE chat go through the same MCP server (broker eats its own dog food via an internal MCP client) so the activity feed is unified
- DeepSeek + OpenAI + a local Ollama model are smoke-tested

## Phase 4 — Knowledge & ergonomics

**Goal:** make the model less dumb. Add Resources and Prompts that encode common workflows.

**Done when:**
- Scan results exposed as MCP Resource at `cegm://scan/{scan_id}` so the model can re-read state without burning tool calls
- Module map exposed as `cegm://modules/{pid}`
- Prompts: `find-numeric-stat`, `follow-pointer-chain`, `dissect-struct-at`, parameterized by user-typed value
- A small "starter" knowledge pack: how to interpret common value type guesses (low int → flag/index; high int → packed → check as float; nontrivial float in [0.0, 1.0] → progress / percentage)

## Phase 5 — Distribution polish

**Goal:** something a non-developer can install in 60 seconds.

**Done when:**
- One-shot Windows installer (PowerShell script in `scripts/install.ps1`) detects CE, copies plugin, installs broker via `uv`, drops example MCP client config files
- Uninstall script reverses cleanly
- README has install / quickstart / troubleshooting
- Tagged `v0.1.0` release on GitHub with release notes

## Out of scope (for now)

- Forking CE source / Lazarus build pipeline — see ADR-0001
- Multi-user / remote broker — single-user localhost only
- Online / multiplayer / anti-cheat-evasion features — explicit non-goal
- Mobile / Linux CE support — Windows only at first; CE on Linux/macOS via Wine is unsupported until Phase 1 stabilizes
