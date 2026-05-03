# Tool Spec — what the LLM can call

This file is the contract between the broker (MCP server) and the CE plugin. Every tool listed here must have:

1. A signature in `broker/src/cegm_broker/tools.py` decorated with `@mcp.tool`.
2. A handler entry in `plugin/lib/tools.lua` for the same `method` name.
3. A test fixture in `broker/tests/`.

Tools are identified by `snake_case` names. Argument and return shapes are JSON-Schema-compatible (the MCP spec already mandates this for `inputSchema`). Where the source of truth is a CE Lua API, the relevant function is cited with a wiki link.

Phase column: which roadmap phase this tool ships in. P1 = MVP.

## Conventions

- Addresses: hex strings prefixed `0x` (e.g. `"0x7FF6A1234567"`) — JSON numbers can't safely hold 64-bit integers in all clients.
- Module-relative addresses: `"<module>+<hex>"` (e.g. `"game.exe+1A2B3C"`), matching CE's own format.
- Value types (`vt`): `"byte" | "word" | "dword" | "qword" | "single" | "double" | "string" | "ustring" | "bytes" | "binary" | "all"` — mirrors CE's `vtByte..vtAll` (research §2). Broker translates to CE constants.
- Scan compares (`op`): `"exact" | "bigger" | "smaller" | "between" | "incremented" | "decremented" | "changed" | "unchanged" | "unknown"` — mirrors `soExactValue..soUnknownValue`.
- All sizes default to current process bitness; tools that depend on bitness expose an explicit override.
- All tools return `{ ok: true, ... }` on success, raise `ToolError` (FastMCP) on failure.

## Process / attach

| Tool | Phase | Args | Returns | CE Lua |
|---|---|---|---|---|
| `process_list` | P1 | `{ filter?: string }` | `[{ pid, name, bitness }]` | `getProcesslist()` |
| `process_attach` | P1 | `{ pid?: number, name?: string }` | `{ pid, name, bitness, base_addresses: [...] }` | `openProcess`, `getProcessIDFromProcessName` |
| `process_detach` | P1 | `{}` | `{ ok: true }` | (close handle) |
| `process_status` | P1 | `{}` | `{ pid, name, bitness, attached: bool }` | (cached) |

## Memory read / write

| Tool | Phase | Args | Returns | CE Lua |
|---|---|---|---|---|
| `memory_read` | P1 | `{ address: hex, vt: type, count?: int, max_string_len?: int, wide?: bool }` | `{ value: any, raw_bytes_b64?: string }` | `readBytes/readInteger/readFloat/readString/...` |
| `memory_read_many` | P1 | `{ items: [{ address, vt, count?, ... }] }` | `[ { address, value } ]` | batched `read*` |
| `memory_write` | P2 | `{ address, vt, value }` | `{ ok: true, prev?: any }` | `writeBytes/writeInteger/...` |
| `memory_protect_query` | P2 | `{ address, length: int }` | `[{ start, length, protect, state }]` | `VirtualQueryEx` via `executeCodeLocal` |

`memory_read` returns `value` as the natural JSON type (number for ints/floats, string for strings, base64 bytes string for `vt: "bytes"`). Writes accept the same shapes.

## Scanning

| Tool | Phase | Args | Returns | CE Lua |
|---|---|---|---|---|
| `scan_first` | P1 | `{ value: any, vt: type, op?: compare = "exact", value2?: any, range?: [hex, hex], protect?: string, alignment?: int }` | `{ scan_id, count }` | `createMemScan`, `firstScan` |
| `scan_next` | P2 | `{ scan_id, op: compare, value?: any, value2?: any }` | `{ scan_id, count }` | `nextScan` |
| `scan_results` | P1 | `{ scan_id, offset?: int = 0, limit?: int = 100 }` | `{ scan_id, total, items: [{ address, value }] }` | `createFoundList`, indexing |
| `scan_drop` | P1 | `{ scan_id }` | `{ ok }` | (release MemScan + FoundList) |
| `aob_scan` | P2 | `{ pattern: string, module?: string, protect?: string, max_hits?: int = 256 }` | `{ hits: [hex], truncated: bool }` | `AOBScan`, `AOBScanModule` |
| `aob_scan_unique` | P2 | `{ pattern: string, module?: string }` | `{ address: hex \| null }` | `AOBScanUnique` |

`scan_id` is a broker-issued UUID; the underlying `MemScan` and `FoundList` are kept alive on the plugin side until `scan_drop` or session end. Plugin enforces a hard cap of N concurrent scan_ids (default 8) to bound memory.

The full result list is also exposed as a `Resource` at `cegm://scan/{scan_id}` — clients that want everything paged can read the resource instead of looping `scan_results`.

## Pointer chains and structs

| Tool | Phase | Args | Returns | Notes |
|---|---|---|---|---|
| `pointer_resolve` | P1 | `{ base: hex \| modulerel, offsets: [int] }` | `{ address: hex, value?: any }` | walks pointer chain via `readPointer` |
| `pointer_scan` | P3 | `{ address: hex, max_depth?: int = 5, max_offset?: int = 0x1000, time_budget_s?: int = 30 }` | `{ candidates: [{ base, offsets, address }], truncated }` | drives `PointerscanForm` or post-processes `.PTR` (research §2 — no clean Lua API) |
| `dissect_struct` | P3 | `{ address, size?: int = 0x80 }` | `{ fields: [{ offset, vt_guess, value }] }` | uses CE's structure-dissection (`getStructureLinkedToName` etc.) |

Pointer scan in P3 because the CE-side implementation is form-driven and needs more careful design than other tools.

## Cheat table I/O

| Tool | Phase | Args | Returns | CE Lua |
|---|---|---|---|---|
| `address_add` | P1 | `{ description, address, vt, offsets?: [int], active?: bool }` | `{ row_id }` | `getAddressList():createMemoryRecord()` |
| `address_freeze` | P1 | `{ row_id, value?: any }` | `{ ok }` | `MemoryRecord.Active = true` (with optional value pin) |
| `address_unfreeze` | P1 | `{ row_id }` | `{ ok }` | `MemoryRecord.Active = false` |
| `address_remove` | P1 | `{ row_id }` | `{ ok }` | `MemoryRecord:delete()` |
| `address_list` | P1 | `{}` | `[ { row_id, description, address, vt, value, active } ]` | iterate `AddressList` |
| `cheat_table_save` | P2 | `{ path }` | `{ ok }` | save .CT (XML) |
| `cheat_table_load` | P2 | `{ path }` | `{ added: [row_id] }` | load .CT |

`row_id` is the CE-internal `MemoryRecord.ID`. Note from research §9 that `AddressList` mutates concurrently with the user's GUI; tools must re-resolve `row_id` before each access, never cache the `MemoryRecord` userdata across calls.

## Disassembly and code

| Tool | Phase | Args | Returns | CE Lua |
|---|---|---|---|---|
| `disasm` | P2 | `{ address, count?: int = 16 }` | `{ instructions: [{ address, bytes_hex, mnemonic }] }` | `disassemble`, `splitDisassembledString` |
| `lua_exec` | P2 (opt-in) | `{ code: string }` | `{ ok, output: string }` | `loadstring(code)()` — gated by `config.tools.lua_exec_enabled` |

`lua_exec` is an obvious foot-gun. It is off by default; the broker refuses to register the tool unless the user enabled it explicitly in `config.json`. When enabled, every invocation logs the full source to `events.jsonl`.

## Resources (read-only)

| URI template | Phase | Description |
|---|---|---|
| `cegm://process/current` | P1 | attached process snapshot (pid, name, bitness, modules count) |
| `cegm://modules/{pid}` | P1 | loaded module list with base / size |
| `cegm://scan/{scan_id}` | P1 | full result set of a live scan, paged by the resource layer |
| `cegm://addresses` | P1 | current cheat-table address list snapshot |
| `cegm://config` | P1 | user-visible config (sans secrets) |

## Prompts (templates)

| Name | Phase | Parameters | Purpose |
|---|---|---|---|
| `find-numeric-stat` | P4 | `{ stat_name, current_value, value_type? }` | guides the LLM through first-scan → next-scan loop |
| `follow-pointer-chain` | P4 | `{ from_address, target_description }` | guides pointer-scan → resolve → verify |
| `dissect-struct-at` | P4 | `{ address }` | walks a struct, suggests field names |

Prompts are intentionally Phase 4 — they encode workflow knowledge, but they don't unblock any new capability before then.

## Error envelope

```jsonc
// raised as ToolError; FastMCP wraps as MCP error
{
  "code": "process_not_attached" | "invalid_address" | "scan_not_found" |
          "ipc_timeout" | "ce_lua_error" | "tool_disabled" | "validation_failed",
  "message": "human-readable",
  "data": { /* tool-specific */ }
}
```

Codes are namespaced and stable. Adding a new code requires an entry here.

## Version compatibility

The handshake (`hello` line) carries `protocol_version` and a `tools_version` hash. Mismatched protocol version → fatal abort. Mismatched tools_version → log a warning and refuse tools that aren't in both sides' lists. This prevents a stale plugin paired with a new broker (or vice versa) from silently routing to the wrong handler.
