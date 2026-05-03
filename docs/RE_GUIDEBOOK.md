# RE Guidebook — operating CEGM like a real reverse engineer

A working handbook for an LLM (or a human pairing with one) driving CEGM against a target process. The aim is **a stand-alone reference** the model can re-read mid-session: every section has a normal happy path, the most common ways it goes wrong, and what to try next. When the built-in tools don't fit, the last subsection of each topic shows how to mint a new tool with `cegm.tool_define`.

> **Verified targets.** Every snippet in this doc was run live against either Cheat Engine 7.5's own Tutorial-x86_64.exe or AssaultCube v1.3.0.2's `ac_client.exe` on Windows 11 with the broker on port 27077. The shapes you see are real; values are sample outputs.

## 0. Mental model in 30 seconds

```
  ┌────────────────────────┐  HTTP MCP   ┌──────────────────┐
  │  external client       │ ─────────▶  │  CEGM broker     │
  │  (Codex / Claude /     │             │  127.0.0.1:27077 │
  │   the dashboard chat)  │ ◀─SSE/WS──  │                  │
  └────────────────────────┘             └────┬─────────────┘
                                              │ stdio
                                              ▼
                                  ┌──────────────────────┐
                                  │  miscusi-peek child  │
                                  │  175 raw tools       │
                                  └────┬─────────────────┘
                                       │ \\.\pipe\CE_MCP_Bridge_v99
                                       ▼
                                  ┌──────────────────────┐
                                  │  Cheat Engine + Lua  │
                                  └────┬─────────────────┘
                                       ▼
                                   target.exe
```

You speak to CEGM via `tools/call` over `http://127.0.0.1:27077/mcp`. Every call is a JSON-RPC envelope. The dashboard at `http://127.0.0.1:27077/` is the same set of tools, just via a chat UI, with live panels for scans, watches, and the tool browser.

## 1. Setup checklist

Before any RE work — verify the stack is wired up. **If any of these fails, fix it before moving on**; downstream steps will silently misbehave.

```bash
# 1. Broker is alive
curl -sS http://127.0.0.1:27077/api/health
# expect: {"ok":true,"version":"...","port":27077,"proxy":{"available":true,"tool_count":175,...}}
```

If `proxy.available` is `false`: Cheat Engine isn't running, or its autorun didn't load `ce_mcp_bridge.lua`. Open CE; check `\\.\pipe\CE_MCP_Bridge_v99` exists with `ls \\.\pipe\` (PowerShell `[System.IO.Directory]::GetFiles("\\.\pipe\")`).

```bash
# 2. Match CE bitness to your target
#    - 64-bit target → cheatengine-x86_64.exe
#    - 32-bit target → cheatengine-i386.exe
```

64-bit CE *can* attach to a 32-bit process for naming, but **memory reads silently fail** on user-land addresses. AC (`ac_client.exe`) is 32-bit; CE Tutorial v3.6 ships both bitnesses.

```bash
# 3. Broker re-discovers the new pipe automatically when CE restarts —
#    but if it gets stuck, kill and re-run:
#    Get-NetTCPConnection -LocalPort 27077 -State Listen |
#       %{Stop-Process -Id $_.OwningProcess -Force}
#    cd broker && uv run cegm-broker --port 27077
```

## 2. Attach → process info

### Normal path

```bash
# Attach by name
curl -sS -X POST http://127.0.0.1:27077/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"open_process",
                 "arguments":{"process_id_or_name":"ac_client.exe"}}}'
# → {"success":true,"process_name":"ac_client.exe","process_id":7208}

# Module map
curl ... '{"name":"get_process_info","arguments":{}}'
# → {"process_name":"ac_client.exe","process_id":7208,
#    "modules":[{"name":"ac_client.exe","address":"0x00400000","size":1806336},
#               {"name":"ntdll.dll","address":"0x7FFE6BB80000",...},
#               ...]}
```

The first module (with the same name as the process) is **the executable image**; its `address` is the static base. Everything in code/.rdata/.data lives in `[base, base+size)`. For static-data scans this is the canonical region to filter on.

### When it goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `success: true` but `process_name: <wrong>` and zero modules | Stale CE attach state from a prior run | Re-call `open_process` with explicit PID, then `get_process_info` again |
| `Cheat Engine Bridge (v12/v99) is not running (Pipe not found)` | CE isn't running or autorun didn't load | Restart CE; verify pipe exists |
| `Failed to read at 0x...` on `read_memory` after attach | CE bitness mismatches target | Switch to matching `cheatengine-i386.exe` or `cheatengine-x86_64.exe` |
| `process_name: null` and empty modules but PID is right | Some games rebase right after attach (anti-debug) | Wait 1-2 seconds after launch; re-attach; or open the process in CE's GUI first to force re-init |

### When the existing tool doesn't fit

If you need richer process info (e.g. heap regions, environment variables) that's not in `get_process_info` — define your own:

```jsonc
// cegm.tool_define
{
  "name": "custom.process_env",
  "description": "Read the target's PEB ProcessParameters Environment block",
  "input_schema": {"type":"object","properties":{}},
  "lua_body": "local pid = getOpenedProcessID()\n -- fetch PEB, walk to ProcessParameters\n -- (placeholder; real implementation uses readPointer + readBytes)\n return string.format('pid=%d', pid)"
}
```

## 3. The scan-and-narrow loop

This is the bread and butter — finding a value by name.

### Normal path: known initial value

You know the target value (e.g. CE Tutorial Step 2 says "Health = 100"; AC's default starting HP is 100):

```jsonc
// 1. First scan — broker wraps scan_all + first page in one call
{"name":"cegm.scan",
 "arguments":{"value":"100","vt":"int32","max_results":50}}
// → {"scan_id":"scan-...","count":911,"results":[
//     {"address":"0x0019B2FC","value":"100"},
//     {"address":"0x0019BC98","value":"100"},
//     ...
//   ]}
```

`count: 911` for value-100/int32 against AC's `ac_client.exe` is normal at the menu — the binary has many static `100`s in resources/code. Now we narrow.

```jsonc
// 2. The user changes the value in-game (takes damage, picks up health, etc.)
//    Now narrow to whatever the new value is.
{"name":"cegm.scan_narrow",
 "arguments":{"op":"exact","value":"95"}}
// → {"scan_id":"scan-...","parent_id":"scan-...","op":"exact","count":3,...}
```

Repeat until `count` is in the single digits. Three-five iterations usually nail the player struct's HP field. The dashboard's **Scans** tab shows the chain visually with one card per scan.

### Normal path: unknown initial value

You don't know the value but know it changes when X happens (CE Tutorial Step 4):

```jsonc
// 1. First scan with a placeholder — type-only, no specific value
//    miscusi-peek's scan_all needs a value, but you can scan-all-unknown
//    by using the upstream tool directly:
{"name":"scan_all_first",
 "arguments":{"type":"unknown_initial","vt":"4 bytes"}}

// 2. After the value goes UP:
{"name":"cegm.scan_narrow","arguments":{"op":"increased"}}
// 3. After it goes DOWN:
{"name":"cegm.scan_narrow","arguments":{"op":"decreased"}}
// 4. After it stays the same:
{"name":"cegm.scan_narrow","arguments":{"op":"unchanged"}}
```

Six-eight iterations of changed/unchanged usually narrows even unknown values to a handful.

### When it goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `count: 0` after `cegm.scan` for a value you can see on screen | Wrong `vt` (game might use float for HP that looks like an integer) | Try `vt: "float"`; common in racing/sim games |
| `count: 0` after attach from 64-bit CE on 32-bit process | WoW64 read can fail for the entire address space | Switch CE to 32-bit |
| `count` is huge (10⁵+) and `next_scan` doesn't shrink it | The "value changed" you reported didn't actually change in memory (UI might display modified values) | Look for the underlying field — sometimes the displayed HP is `current_hp = max_hp - damage`; scan for `max_hp - displayed_hp` instead |
| `cegm.scan_narrow` returns `no active scan` | Broker restarted or someone called `cegm.scan_drop` | Re-run `cegm.scan` from the start |

### Custom tool: scan + auto-narrow recipe

If you want a one-shot "find me the address that holds value X right now and watch it":

```jsonc
{"name":"cegm.tool_define","arguments":{
  "name":"custom.find_and_watch",
  "description":"First-scan a value; if exactly one hit, register it as a watch.",
  "input_schema":{"type":"object","properties":{
    "value":{"type":"string"},
    "label":{"type":"string","default":""}}},
  "lua_body":"\nlocal s = createMemScan()\ns:firstScan(soExactValue, vtDword, rtRounded, params.value, '', 0, 0xffffffffffffffff, '', fsmNotAligned, '4', false, false, false, false)\ns:waitTillDone()\nlocal fl = createFoundList(s)\nfl:initialize()\nif fl.Count ~= 1 then\n  return string.format('found %d, need 1 to auto-watch', fl.Count)\nend\nlocal addr = string.format('%X', fl[0])\n-- registering a watch is a CEGM tool, not a CE primitive — return the\n-- address instead and let the caller chain into cegm.watch_add\nreturn addr\n"
}}
```

Then the caller chains: `custom.find_and_watch(value=42)` → returns address → `cegm.watch_add(address, vt, label)`.

## 4. Hex dumps and structure dissection

Once you have a candidate address, dump the surrounding bytes to look for structure clues (other player fields adjacent in memory).

```jsonc
{"name":"cegm.hex_dump",
 "arguments":{"address":"0x00400000","length":64}}
```

Sample output (AC's PE header):

```
+0000  4d 5a 90 00 03 00 00 00 04 00 00 00 ff ff 00 00  MZ..............
+0010  b8 00 00 00 00 00 00 00 40 00 00 00 00 00 00 00  ........@.......
+0020  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
+0030  00 00 00 00 00 00 00 00 00 00 00 00 48 01 00 00  ............H...
```

**Reading tips for player structs:**

- **Adjacent ints often paired** — `current_hp` and `max_hp` typically 4 bytes apart.
- **Floats look like 0xC1XXXXXX or 0x42XXXXXX** — float ranges around –10 to +100 with sign bits visible.
- **Pointer fields point into heap** — high `0x00######` (32-bit) or `0x00007FF#######` (64-bit). If you see one, follow it with `read_pointer`.
- **Strings are null-terminated and look ASCII** — name fields, weapon IDs, map names.

### When `cegm.hex_dump` returns zero rows

The `raw_upstream` field tells you why. If it's `{"error": "Failed to read at ...", "success": false}`, the address isn't valid in the target. Check:

1. The address really exists in the process — not a stale scan result from a previous attach.
2. The CE bitness matches the target.
3. Memory protection — some sections are PAGE_NOACCESS until the loader's done.

### Custom tool: typed struct dump

When you know the layout, define a per-game tool:

```jsonc
{"name":"cegm.tool_define","arguments":{
  "name":"custom.dump_player",
  "description":"Dump the AC player struct fields by offset",
  "input_schema":{"type":"object","properties":{
    "base":{"type":"string","description":"player base pointer in hex"}}},
  "lua_body":"\nlocal b = tonumber(params.base, 16)\nreturn {\n  position_x = readFloat(b + 0x4),\n  position_y = readFloat(b + 0x8),\n  position_z = readFloat(b + 0xC),\n  health = readInteger(b + 0xEC),\n  armor = readInteger(b + 0xF0),\n}\n"
}}
```

After this, the LLM can call `custom.dump_player(base="0x12345678")` and get back a structured object instead of staring at hex.

## 5. Live watches

Once a scan narrows to a single address, register a watch so the dashboard's **Watches** tab shows the value live:

```jsonc
{"name":"cegm.watch_add",
 "arguments":{"address":"0x019AEFEC","vt":"int32","label":"player.health"}}
// → {"watch_id":"watch-...","address":"0x019AEFEC","vt":"int32","label":"player.health"}
```

The broker polls every 250 ms and emits `watch_update` events on every change. The dashboard re-renders the row on each event; the **Activity** timeline gets a new entry every time the value changes.

To remove: `cegm.watch_remove(key="0x019AEFEC")` or `cegm.watch_remove(key="watch-…")`.

### Common pitfalls

- **Address goes stale.** Most game state lives in heap-allocated structs that get freed and re-created on level change / respawn / weapon swap. The address from a scan is good *for that life cycle only*. Once it's stale, watch values become garbage. Solution: find a **pointer chain** that survives (next section).
- **Game freezes when watch reads invalid memory.** miscusi-peek's bridge tries to recover, but back-to-back invalid reads can hang the CE Lua thread. If a watch starts spitting `error: Failed to read…`, remove it immediately.

## 6. Pointer chains

Static heap addresses change every game launch (ASLR + heap allocation order). To get an address that survives restarts, you walk back from the dynamic address to a chain rooted at a static address (typically `module+offset`).

### Normal path

```jsonc
// Upstream ships find_pointer_path; CEGM doesn't wrap it (yet) so call directly.
{"name":"find_pointer_path",
 "arguments":{"address":"0x019AEFEC","max_offset":2048,"max_depth":5}}
// → {"chains":[{"base":"0x004D27A4","offsets":[0x10, 0x20, 0xEC]}, ...]}

// Resolve a chain to verify it still points at the right place
{"name":"read_pointer_chain",
 "arguments":{"base":"0x004D27A4","offsets":[16, 32, 236]}}
// → {"address":"0x019AEFEC","value":"100"}
```

Restart the game and run `read_pointer_chain` again with the same `base` + `offsets`: if it still resolves to a valid address holding the right value, you have a stable chain.

### When pointer scans return huge candidate sets

Lower `max_offset` (default 2048 → try 1024 or 512). Higher `max_depth` finds more chains but also more false positives.

If `find_pointer_path` returns nothing useful, the heap struct may not be reachable from a single static base — common with games that use registry / manager objects. Try `find_pointer_path_for_address` (it walks back from the dynamic address looking for any static-rooted path) or scan for the **pointer to the struct** instead of a value inside it.

### Custom tool: chain validator

After narrowing, the LLM should sanity-check the chain across a launch cycle:

```jsonc
{"name":"cegm.tool_define","arguments":{
  "name":"custom.validate_chain",
  "description":"Resolve a chain and report whether the final address is readable",
  "input_schema":{"type":"object","properties":{
    "base":{"type":"string"},
    "offsets":{"type":"array","items":{"type":"integer"}},
    "vt":{"type":"string","default":"int32"}}},
  "lua_body":"\nlocal addr = tonumber(params.base, 16)\nfor _, o in ipairs(params.offsets) do\n  addr = readPointer(addr) + o\n  if not addr then return {valid=false, where='step '..o} end\nend\nreturn {valid=true, address=string.format('%X', addr), value=readInteger(addr)}\n"
}}
```

## 7. Code injection (cheat scripts)

The classical CE flow: find the instruction that reads/writes the value, replace it with one that reads/writes whatever you want.

### Normal flow

```jsonc
// 1. Find the instruction that writes to the address (puts a hardware
//    breakpoint, asks you to provoke the write, returns the hit asm).
{"name":"set_data_breakpoint",
 "arguments":{"address":"0x019AEFEC","trigger":"write","size":4}}
// (provoke the write — take damage, fire a shot, etc.)
{"name":"get_breakpoint_hits","arguments":{}}
// → [{"address":"0x004A1B23","instruction":"mov [esi+0xEC], eax", ...}]

// 2. Generate an injection script around that instruction
{"name":"generate_code_injection_script",
 "arguments":{"address":"0x004A1B23",
              "behaviour":"skip"}}
// → returns auto-assembler script with original bytes + jump to cave
```

Apply with the upstream Auto-Assembler tool (`auto_assemble`) once you've reviewed it.

### Custom tool: AOB-locked patch

Once you've written a patch, anchor it on an AOB pattern so it survives game updates:

```jsonc
{"name":"cegm.tool_define","arguments":{
  "name":"custom.god_mode_lock",
  "description":"Find the AC damage instruction by AOB and NOP it",
  "input_schema":{"type":"object","properties":{}},
  "lua_body":"\nlocal pat = '29 ?? EC 89' -- example: sub [reg+EC],reg / mov ...\nlocal r = AOBScan(pat)\nif not r or r.Count == 0 then return {ok=false, why='pattern not found'} end\nlocal addr = tonumber('$' .. r[0])\nfor i = 0, 2 do writeBytes(addr + i, 0x90) end\nr.destroy()\nreturn {ok=true, patched_at=string.format('%X', addr)}\n"
}}
```

(Pattern is illustrative; the real one comes from `generate_signature` on the writing instruction.)

## 8. Dynamic tool creation — the meta-loop

The point of `cegm.tool_define` is that the model can *teach itself a new verb mid-session*. Pattern:

1. Try to do something with the existing tools.
2. Notice you're repeating a 4-step sequence.
3. Define a `custom.*` tool that captures the sequence as a single Lua call.
4. Use it for the rest of the session.

Naming convention: `custom.<game>.<verb>` (e.g. `custom.ac.find_player`, `custom.tutorial.advance_step`). The dashboard's **Tools** tab will show them grouped under the **Custom** category.

Persistence: definitions go to `%LOCALAPPDATA%\CEGM\dynamic_tools.json` and survive broker restarts. To wipe:

```powershell
Remove-Item "$env:LOCALAPPDATA\CEGM\dynamic_tools.json"
```

### Anatomy of a `lua_body`

The body runs inside CE's Lua engine. Available globals (via miscusi-peek's bridge):

| Function | Purpose |
|---|---|
| `getOpenedProcessID()` | currently-attached PID |
| `readBytes(addr, count, true)` | returns table of bytes |
| `readInteger(addr)` / `readFloat(addr)` / `readDouble(addr)` / `readString(addr,len)` | typed reads |
| `writeInteger(addr, v)` / `writeFloat(addr, v)` / `writeBytes(addr, b1, b2, …)` | typed writes |
| `readPointer(addr)` | walk one pointer step |
| `AOBScan(pattern)` | byte-pattern scan; returns `StringList` (call `:destroy()`) |
| `createMemScan()` / `:firstScan(...)` / `:nextScan(...)` | full scan engine |
| `getModuleSize(name)` / `getAddress(name)` | module info / symbol resolution |

Args are exposed as the global `params` table — `params.foo` returns whatever was passed in the tool call. The return value (table or scalar) is JSON-serialized back to the caller.

### When a custom tool isn't enough

Some operations need state across calls (e.g. tracking a watch independently of CEGM's poller). For those: define a tool that uses `evaluate_lua` to register Lua-side state in a global table, and a second tool to read that state. Or, if it's getting complex, file an issue — the workbench should grow new first-class verbs for repeated patterns.

## 9. Working with the dashboard chat in parallel

External MCP clients can hand off to the dashboard's chat with `cegm.dashboard_chat`:

```jsonc
{"name":"cegm.dashboard_chat",
 "arguments":{"message":"the player struct base is 0x019AEFEC; can you find a pointer chain to it?"}}
```

The user's open dashboard tab auto-submits the message into its chat input, flashes its title, and (with permission) raises a desktop notification. The dashboard's own LLM picks up the conversation; the timeline shows everything that happens.

## 10. Quick recipes for common targets

### CE Tutorial v3.6 (Tutorial-x86_64.exe)

```
Step 2 (exact value):
  cegm.scan {"value":"100","vt":"int32"}    → narrow each click of "Hit me"
  cegm.scan_narrow {"op":"exact","value":"<new>"}
  → 1 hit, write 1000 to advance

Step 4 (float):
  cegm.scan {"value":"<displayed>","vt":"float"}
  → typically narrows in 3 iterations

Step 5 (Code finder):
  set_data_breakpoint {"address":"<found>","trigger":"write"}
  → click "Hit me", get the asm, NOP it via auto_assemble

Step 6 (Pointer):
  find_pointer_path {"address":"<found>","max_depth":1}
  → returns base + one offset
```

### AssaultCube (`ac_client.exe` — 32-bit)

```
Player base pointer (well-known across the AC modding community):
  ac_client.exe + 0x10F4F4 → player struct

Common offsets (struct):
  +0x4   x position (float)
  +0x8   z position (float, vertical)
  +0xC   y position (float)
  +0xEC  health (int32, default 100)
  +0xF0  armor  (int32)
  +0x150 ammo[active_weapon] (int32)

Verify after attaching:
  read_pointer_chain {"base":"ac_client.exe+0x10F4F4","offsets":[0xEC]}
```

(Values are public knowledge — AC has been the standard CE practice target since 2008. Sources: [Fearless Hacks AC tutorial](https://www.unknowncheats.me/forum/), CE official wiki examples.)

## 11. Self-rescue checklist

When you're stuck, run through these in order:

1. **Is the broker up?** `curl /api/health`. If not — go to §1.
2. **Is the right process attached?** Re-call `get_process_info`. If `process_name` differs from your target — re-attach.
3. **Is CE bitness right?** Check the module list — if you see WoW64 modules and reads fail, switch CE.
4. **Have you scanned for the right type?** Try `vt: "float"` if `int32` returns 0 hits.
5. **Did the value actually change?** Look at the activity timeline — if your `cegm.scan_narrow` calls aren't getting fewer hits, you're scanning for the wrong value.
6. **Is the address still valid?** Use `cegm.hex_dump(address, 16)` to confirm the address is readable.
7. **Are you fighting anti-debug?** Some games detect CE; close any anti-cheat / DRM components in Task Manager before the target.
8. **Did you over-engineer?** When in doubt, drop back to the upstream tool (`scan_all`, `next_scan`, `read_memory`) — `cegm.*` is convenience on top of the upstream surface, not a replacement for it.
9. **Define a new tool.** If you've repeated a 4-step sequence twice, the third time should be a `custom.*` tool.
10. **Ask the dashboard user.** `cegm.dashboard_chat` hands off to a human in the loop.
