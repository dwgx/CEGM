# Tool Spec — what the LLM can call

CEGM is a thin layer on top of [miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge). Tools come from three places:

1. **Proxied tools** — the ~173 tools from miscusi-peek, exposed verbatim under their original names (`open_process`, `read_memory`, `scan_all`, `aob_scan_module`, `set_breakpoint`, `evaluate_lua`, …). We do not redocument them here; their canonical reference is [miscusi-peek's README](https://github.com/miscusi-peek/cheatengine-mcp-bridge#available-tools) and the runtime `tools/list` MCP call.
2. **CEGM extras** — a small `cegm.*` namespace documented below. Implemented in `broker/src/cegm_broker/mcp_extras.py`; tested in `broker/tests/test_extras.py`.
3. **Custom (runtime-defined) tools** — anything starting with `custom.`. Defined via `cegm.tool_define` at runtime, persisted to `%LOCALAPPDATA%\CEGM\dynamic_tools.json`, dispatched by wrapping a stored Lua snippet in a small bootstrap and forwarding through proxied `evaluate_lua`.

## Conventions

- Addresses: hex strings prefixed `0x`, or `<module>+<hex_offset>` (e.g. `ac_client.exe+0x18AC04`).
- Value types (`vt`): `byte` / `int8` / `word` / `int16` / `dword` / `int` / `int32` / `qword` / `int64` / `float` / `double` / `string` — case-insensitive.
- Every tool returns a JSON text block describing the result. Failures raise `ValueError` / `RuntimeError` / `KeyError` which the broker surfaces as MCP errors with the original message.
- Most tools also publish a versioned event on the WebSocket bus (e.g. `scan_started`, `watch_update`, `dashboard_chat_request`). The dashboard's panels listen on these.

## Shipped tools (current as of v0.1.0a1)

### Observability

#### `cegm.activity_recent`

Return the most recent CEGM events (tool calls, chat turns, scan / watch lifecycle, broker / CE status).

- **Args:** `{ limit?: int = 50, max=500 }`
- **Returns:** `{ events: Event[], count: int }`
- Use when the LLM needs to recall what just happened without re-running tools.

#### `cegm.dashboard_chat`

Hand off a chat message to the CEGM browser dashboard.

- **Args:** `{ message: string }` (non-empty)
- **Returns:** `{ ok, url, delivered_at, dashboard_subscribers, note }`
- **Side effect:** `dashboard_chat_request` event broadcast on the WebSocket bus; the dashboard's chat input auto-submits the message; tab title flashes; (with permission) a desktop notification appears.

### Scan workbench

#### `cegm.scan`

First-scan wrapper. Calls upstream `scan_all` then immediately fetches the first page so the LLM doesn't have to issue a second `get_scan_results`.

- **Args:** `{ value: string, vt?: string = "int32", max_results?: int = 50, protection?: string = "+W-C" }`
- **Returns:** `{ scan_id, value, vt, count, page_size, results: [{address, value}] }`
- **Side effect:** publishes `scan_started`. Broker keeps the first page snapshot so the dashboard's Scans tab can re-render it.

#### `cegm.scan_narrow`

Narrow the most recent scan via upstream `next_scan`.

- **Args:** `{ op?: "exact"|"bigger"|"smaller"|"between"|"increased"|"decreased"|"changed"|"unchanged", value?: string, max_results?: int = 50 }`
- **Returns:** `{ scan_id, parent_id, op, count, page_size, results }`
- **Errors:** `ValueError("no active scan to narrow")` if `cegm.scan` hasn't been called this session.
- **Side effect:** publishes `scan_narrowed`.

#### `cegm.scan_drop`

Forget the most recent (or named) scan record. UI hygiene only; doesn't release upstream's `MemScan`.

- **Args:** `{ scan_id?: string }`  (defaults to most recent)
- **Returns:** `{ removed: bool, scan_id }`
- **Side effect:** publishes `scan_dropped`.

### Live watches

The broker polls every watched address every ~250 ms and emits `watch_update` events on every change (plus a heartbeat every ~2 s).

#### `cegm.watch_add`

Register an address as a live watch.

- **Args:** `{ address: string, vt?: string = "int32", label?: string = "" }`
- **Returns:** `{ watch_id, address, vt, label }`
- Idempotent on `(address, vt)` — re-adding updates the label.
- **Side effect:** `watch_added` then `watch_update` on every change.

#### `cegm.watch_remove`

Stop watching an address.

- **Args:** `{ key: string }`  (a `watch_id` or the literal address)
- **Returns:** `{ removed: bool, key }`

#### `cegm.watch_list`

Snapshot of currently-active watches.

- **Args:** `{}`
- **Returns:** `{ watches: [{watch_id, address, vt, label, last_value, last_seen_ts, error}], count }`

### Memory inspection

#### `cegm.hex_dump`

Read a region and return rows of 16 bytes formatted as offset / hex / ASCII. Handy for struct dissection without firing up CE's memory view.

- **Args:** `{ address: string, length?: int = 64, max=4096 }`
- **Returns:** `{ address, length, rows: [{offset, hex, ascii}], raw_upstream }`
- **Failure mode:** if upstream `read_memory` fails, `rows: []` and `raw_upstream` carries the upstream error envelope.

### Self-extension (runtime-defined tools)

#### `cegm.tool_define`

Register a runtime-defined tool. Names must start with `custom.` so they cannot shadow built-in or upstream tool names.

- **Args:** `{ name: string (must match ^custom\.[A-Za-z_][A-Za-z0-9_.-]*$), description?: string, input_schema?: object, lua_body: string (non-empty) }`
- **Returns:** `{ ok, tool: {name, description, input_schema, lua_body, created_at, updated_at} }`
- **Side effect:** persists to `%LOCALAPPDATA%\CEGM\dynamic_tools.json`; emits `dynamic_tool_defined`; appears in the next `tools/list`.

The `lua_body` runs inside CE's Lua engine on every call. It sees:

- `params` — the call arguments rendered as a Lua table literal (no JSON parsing inside Lua).
- All globals miscusi-peek's bridge exposes: `readBytes`, `readInteger`, `readFloat`, `readDouble`, `readString`, `readPointer`, `writeInteger`, `writeFloat`, `writeBytes`, `getOpenedProcessID`, `getAddress`, `getModuleSize`, `AOBScan`, `createMemScan`, etc.

The body's return value is run through an inline Lua → JSON encoder, so a body can `return {hp=100, pos={1,2,3}}` naturally and the caller gets that as JSON. Errors raised inside the body are caught and surfaced as `{"error": "<message>"}`.

> **Bridge bytestream caveat.** miscusi-peek's named-pipe JSON-RPC framing corrupts on certain non-ASCII UTF-8 sequences (em dashes, box-drawing characters). Keep your `lua_body` ASCII-only or use Lua escapes for non-ASCII string literals.

#### `cegm.tool_undefine`

Remove a custom tool.

- **Args:** `{ name: string }`
- **Returns:** `{ removed: bool, name }`
- **Side effect:** removes from disk; emits `dynamic_tool_undefined`.

#### `cegm.tool_list_custom`

List runtime-defined tools.

- **Args:** `{}`
- **Returns:** `{ tools: CustomTool[], count }`

## Events on the WebSocket

The dashboard subscribes to `ws://127.0.0.1:27077/events`. Each frame is one JSON object:

```jsonc
{
  "ts": "2026-05-04T03:55:00.000Z",
  "id": "evt-…",
  "kind": "tool_called" | "tool_result" | "tool_error"
        | "chat_user" | "chat_assistant" | "chat_token"
        | "scan_started" | "scan_narrowed" | "scan_dropped"
        | "watch_added" | "watch_update" | "watch_removed"
        | "dashboard_chat_request"
        | "dynamic_tool_defined" | "dynamic_tool_undefined" | "dynamic_tool_called"
        | "broker_status",
  "data": { /* kind-specific */ }
}
```

`watch_update` carries `{ watch_id, address, vt, label, value, ts, changed }` (or `{ ..., error }` on a read failure).

## Planned (not yet shipped)

The original `TOOL_SPEC.md` listed these — they're tracked in [ROADMAP.md](ROADMAP.md) Phase 4 and will arrive together as the safety / undo layer.

- `cegm.preview_write` — stage a memory write without applying.
- `cegm.commit_pending` / `cegm.cancel_pending` — confirm or discard.
- `cegm.snapshot_take` / `snapshot_restore` / `snapshot_list` — labeled rollback points.
- `cegm.recipe_list` / `recipe_run` — guided multi-tool workflows for `find-numeric-stat`, `follow-pointer-chain`, `dissect-struct-at`, `code-cave-inject`, `aob-signature-lock`.

## Adding a new CEGM tool

1. Add a `types.Tool(...)` entry to `EXTRAS_TOOL_DEFS` in `broker/src/cegm_broker/mcp_extras.py`.
2. Add an `if name == "cegm.your_tool":` branch to `dispatch()` in the same file.
3. Document it here under the right subsection.
4. Add a test in `broker/tests/test_extras.py` (use the `_make_proxy(...)` helper if you need a fake upstream).
5. Run `uv run ruff check . && uv run mypy && uv run pytest` — all green before committing.

If the new behavior is something an LLM might mint at runtime instead, consider whether `cegm.tool_define` already handles it — adding a custom tool from the LLM side requires no broker code change.
