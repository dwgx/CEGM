# RE Workbench plan — making CEGM feel like a reverse engineer

This is the working plan for moving CEGM from "LLM with 175 raw tools" to "LLM-driven reverse-engineering workbench". Based on a real-machine smoke run on the CE Tutorial v3.6 process: attach, scan, paged result fetch, hex read all worked, but the experience exposed concrete friction points and missing surfaces.

## Friction log (observed 2026-05-03 against Tutorial-x86_64.exe)

1. **Scan API is split into two calls.** `scan_all` returns only `{count, success}`; you must follow with `get_scan_results({offset, limit})` to see addresses. Models that expect inline results burn an extra round-trip every scan. **Fix idea:** add a `cegm.scan` wrapper that returns a `scan_id` + the first page in one shot, and stable-pages on subsequent calls.
2. **Tool naming is inconsistent.** `scan_all` (first scan) and `next_scan` (filter scan) live at different verb levels; `aob_scan_unique` and `find_pointer_path` use different conventions. **Fix idea:** in `cegm.list_tools` proxy add a `_meta.category` tag and group the dashboard's "Tools" view accordingly.
3. **Scan results render as a JSON blob in the activity timeline.** With 107 hits the raw block is unreadable. The user can't click an address to watch it, can't sort by address/value, can't narrow without re-typing. **Fix idea:** new "Scans" right-rail tab.
4. **No live watch mechanism.** After a scan narrows to a single address, the natural next step is "watch this address while I poke the game". Currently the LLM has to call `read_memory` in a loop. **Fix idea:** `cegm.watch_add(address, vt)` registers an address; broker polls + emits `watch_update` events; dashboard renders a small live grid.
5. **No memory hex viewer.** `read_memory` returns a hex string blob; a 256-byte read is a wall of text. **Fix idea:** dashboard component that takes `(address, length)` and renders 16-byte rows with offset / hex / ASCII columns.
6. **No disassembly viewer.** `disassemble` returns line-broken text without syntax highlighting; following a pointer chain by reading text is painful. **Fix idea:** dashboard component that lays out `(address, bytes_hex, mnemonic, args)` rows with click-to-jump on operands.
7. **Pointer-chain UX is "type N offsets, get a hex".** No visual chain. **Fix idea:** chain visualizer — boxes for each level, hover shows the pointer value at that step.
8. **AOB pattern editing is string-based and error-prone.** `\x?? \x4C` style hand-typing. **Fix idea:** AOB pattern panel with byte-grid + wildcard cells; export to upstream tool.
9. **Tool descriptions are short and don't compose.** A model planning "find HP, write a high value" has to discover `scan_all` → `get_scan_results` → `next_scan` → `write_integer` from terse one-liners. **Fix idea:** ship a small `cegm.help(topic)` tool that returns recipe-style guidance for common tasks, keyed by `find_stat`, `pointer_chain`, `code_inject`, etc.
10. **No recipes.** Tutorial-style workflows (find a 4-byte stat, follow a multi-level pointer, do a code-cave injection) are repeated in every session. **Fix idea:** MCP `Prompt` definitions for each, parameterized.
11. **No "what changed" view.** After a write, no easy way to confirm the change actually reached the target without re-reading. **Fix idea:** the dashboard already publishes `tool_called`/`tool_result`; add `before/after` diff data inside `result` for memory-write tools.
12. **No undo / snapshot.** Once you write a value, returning to baseline means remembering what was there. **Fix idea:** the long-promised `cegm.snapshot_*` triplet from [TOOL_SPEC.md](TOOL_SPEC.md). Auto-snapshot on first write per session.

## Proposed Phase 2 features

Grouped by surface. Each item names the responsible file(s) and the new MCP / WebSocket contract.

### A. Scan workbench

| Item | Files | New contract |
|---|---|---|
| `cegm.scan` (one-shot wrapper) | `broker/.../mcp_extras.py` | tool: `cegm.scan(value, vt, op, region?, alignment?, max_results?=200)` → `{scan_id, count, results: [{address, value}]}` |
| `cegm.scan_narrow` | same | `cegm.scan_narrow(scan_id, op, value?)` — proxies `next_scan`, returns same shape |
| `cegm.scan_drop` | same | release upstream cache if any |
| Scans panel | `web/js/scans.js`, new `web/index.html` tab | renders the live scan list, pagination, "narrow" / "watch" / "write" actions per row |
| WebSocket events | bus | `scan_started`, `scan_narrowed`, `scan_dropped` |

### B. Live watches

| Item | Files | New contract |
|---|---|---|
| `cegm.watch_add` / `watch_remove` / `watch_list` | `mcp_extras.py` | adds an address to a polling set |
| Watch poller | `broker/.../watches.py` (new) | asyncio task reads each watched address every ~250 ms, fans out `watch_update` events on change |
| Watches panel | `web/js/watches.js`, new tab | live-updating grid: address / type / value / Δ since last change / [unfreeze/freeze/edit] |

### C. Memory hex view

| Item | Files | New contract |
|---|---|---|
| `cegm.hex_dump(address, length, vt_overlay?)` | `mcp_extras.py` | returns rows of 16 bytes + ASCII; `vt_overlay` lets the model annotate "this 4-byte run is an int" |
| Hex pane | `web/js/hex.js` | inline component; opens from a row's "Hex" action; click on a row navigates by ±16 bytes |

### D. Disassembly view

| Item | Files | New contract |
|---|---|---|
| `cegm.disasm_at(address, count?=16)` | `mcp_extras.py` | returns rows `{address, bytes_hex, mnemonic, args, refs?}` after walking instruction lengths |
| Disasm pane | `web/js/disasm.js` | syntax-highlighted lines, click on call/jmp target to follow |

### E. Pointer chain visualizer

| Item | Files | New contract |
|---|---|---|
| Existing `read_pointer_chain` is fine | upstream | — |
| Chain pane | `web/js/chain.js` | takes `(base, offsets[])`, shows boxes with the pointer at each step; updates live if the chain is also a watch |

### F. Recipes & prompts

| Item | Files |
|---|---|
| `cegm.recipe_list()` / `cegm.recipe_run(name, args)` | `mcp_extras.py` |
| Built-in recipes | `broker/.../recipes/{find_numeric_stat,follow_pointer_chain,find_what_writes,code_cave_inject,aob_signature_lock}.py` |
| MCP `Prompt` definitions | `broker/.../prompts.py` |

Initial recipes:

- **find_numeric_stat(stat_name, current_value, value_type?)** — drives scan_first → "ask user to change the value" → scan_next loop until ≤ 5 hits, then proposes which to watch.
- **follow_pointer_chain(target_address)** — calls upstream `find_pointer_path`, returns the shortest base+offsets chain.
- **find_what_writes(address)** — sets a hardware breakpoint, asks user to perform the action, lists hit instructions.
- **code_cave_inject(target_instruction, replacement_asm)** — finds a code cave near the target, generates AOB, builds an aa script that jumps in/out.
- **aob_signature_lock(address)** — generates a unique AOB pattern that re-finds `address` after relocation.

### G. Smarter tool descriptions / categorization

| Item | Files |
|---|---|
| Proxy tool list with `_meta.category` | `broker/.../mcp_server.py` |
| Categories | `process` `memory` `scan` `pointer` `disasm` `breakpoint` `inject` `cheat_table` `cegm` |
| Dashboard tool browser | `web/js/tools.js` (new) | searchable, grouped panel users can read while they're stuck |

### H. Diff + undo

| Item | Files |
|---|---|
| Memory-write event payload includes `before`/`after` | `mcp_extras.py` (wrap upstream `write_*`) |
| `cegm.snapshot_take` / `restore` / `list` | `mcp_extras.py` |
| Auto-snapshot on first write per session | gated by `safety.snapshot_on_first_write` (already in config) |
| Diff styling on timeline rows | `web/js/timeline.js` |

## Priority ordering

Phase 2 (next): **A** + **B** + **C** + **G** — scan workbench, live watches, hex view, categorized tool browser. These four together unlock the realistic RE tutorial loop (scan → narrow → watch → poke → watch).

Phase 3: **D** + **E** + **F** — disasm, chain visualizer, recipes. These are the second-half of "real RE" — debugging and code injection.

Phase 4: **H** — undo/diff. Polish layer; matters once users are doing destructive work routinely.

## Why this list and not "more tools"

The 175 upstream tools cover almost every operation a real RE engineer touches. The bottleneck is **state visibility** (the user can't see what scans are live, what's being watched, what the current memory layout is) and **discoverability** (which of the 175 tools fits the current intent). Both are dashboard-layer problems, not new-MCP-tool problems. Phase 2 is mostly UI + a thin MCP wrapper layer that gives the dashboard something coherent to render.

## Open questions

- **Symbol resolution** — `get_symbol_address` exists upstream; do we want a side-panel showing the symbol table per module?
- **Cross-process attach** — useful for parent-child games (launcher → game). Not in this plan; revisit if a real game needs it.
- **DBVM / kernel watches** — upstream supports them; UX is hairy. Plan a separate "advanced" tab gated by an opt-in setting.
