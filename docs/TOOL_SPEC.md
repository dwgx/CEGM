# Tool Spec — what the LLM can call

CEGM is a thin layer on top of [miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge). Tools come from two places:

1. **Proxied tools** — the ~180 tools from miscusi-peek, exposed verbatim under their original names (e.g. `attach_process`, `read_memory`, `aob_scan`, `pointer_scan`, `disassemble`, `set_breakpoint`, …). We do not redocument them here; their canonical reference is [miscusi-peek's README](https://github.com/miscusi-peek/cheatengine-mcp-bridge#available-tools) and the runtime `tools/list` MCP call.
2. **CEGM extras** — a small namespace `cegm.*` documented below. Every CEGM-namespaced symbol is implemented in our broker; none touch CE directly. They call back into proxied tools to read or write memory.

This file is the contract for the **CEGM extras**. Every tool here must have:

1. A signature in `broker/src/cegm_broker/tools.py` decorated with `@mcp.tool`.
2. A handler with type hints and a Pydantic input model.
3. A test in `broker/tests/test_tools_cegm.py`.

## Conventions

- All addresses are hex strings prefixed `0x` to avoid 64-bit JSON-number issues.
- Value types match miscusi-peek's accepted set so previews/snapshots compose cleanly with their writes.
- Every CEGM tool returns `{ ok: true, ... }` on success or raises `mcp.server.fastmcp.ToolError` with a stable `code` on failure.
- All tools emit one or more events on the broker's event bus; events are versioned (`event_v: 1`).

## Tools

### `cegm.preview_write`

Stage a write without applying it. Useful when the LLM has determined an action but wants the user (or a higher-confidence pass) to confirm.

**Args:** `{ address: hex, vt: type, value: any, label?: string }`
**Returns:** `{ ticket_id: uuid, current_value: any, would_become: any }`
**Side effects:** `event_preview_pending` broadcast to dashboard subscribers; appended to `cegm://activity/recent`.

### `cegm.commit_pending`

Apply a previously staged preview. Idempotent on the same `ticket_id`; subsequent calls return `{ ok: true, already_committed: true }`.

**Args:** `{ ticket_id: uuid }`
**Returns:** `{ ok, address, before: any, after: any }`
**Side effects:** invokes the appropriate proxied `memory_write*` tool; `event_preview_committed` broadcast.

### `cegm.cancel_pending`

Discard a preview. No-op if already committed.

**Args:** `{ ticket_id: uuid }`
**Returns:** `{ ok, was_pending: bool }`

### `cegm.snapshot_take`

Capture current values at all CEGM-watched addresses (the addresses the user has added to the in-CE address list, plus any addresses the LLM has read or written this session).

**Args:** `{ label?: string }`
**Returns:** `{ snapshot_id: uuid, address_count: int, label: string }`
**Storage:** `%LOCALAPPDATA%\CEGM\snapshots\<session_id>\<snapshot_id>.json`

### `cegm.snapshot_restore`

Atomically restore values at every address captured in a snapshot. Fails fast if any address is currently invalid (e.g. process detached); no partial restore.

**Args:** `{ snapshot_id: uuid }`
**Returns:** `{ ok, restored: int, skipped: [{ address, reason }] }`
**Side effects:** invokes proxied `memory_write*` per address; emits a single `event_snapshot_restored` summarizing the diff.

### `cegm.snapshot_list`

**Args:** `{}`
**Returns:** `[ { snapshot_id, label, taken_at, address_count } ]`

### `cegm.recipe_list` (Phase 3)

**Args:** `{}`
**Returns:** `[ { name, description, args_schema, prompt_id } ]`

Initial recipes shipped: `find-numeric-stat`, `follow-pointer-chain`, `dissect-struct-at`.

### `cegm.recipe_run` (Phase 3)

Drive a multi-step workflow under a single LLM context. The recipe is implemented internally as an MCP `Prompt` plus a small state machine that issues tool calls in sequence.

**Args:** `{ name: string, args: object }`
**Returns:** `{ ok, summary: string, results: object }`

## Resources

| URI | Phase | Description |
|---|---|---|
| `cegm://activity/recent?limit=N` | P1 | last N events (tool calls, chat turns, status). Default `limit=50`, max `200`. |
| `cegm://snapshots` | P3 | listing identical to `cegm.snapshot_list` |
| `cegm://snapshots/{id}` | P3 | full snapshot contents |
| `cegm://config` | P1 | sanitized view of runtime config (no secrets) |

Resources are read-only and have no side effects, per MCP semantics. They exist so a model can re-read state without burning a tool budget.

## Events on the WebSocket

The dashboard subscribes to `ws://127.0.0.1:27077/events`. Frames are JSON objects, one event per frame:

```jsonc
{
  "ts": "2026-05-03T14:22:01.123Z",
  "kind": "tool_called" | "tool_result" | "tool_error"
        | "chat_user" | "chat_assistant" | "chat_token"
        | "preview_pending" | "preview_committed" | "preview_canceled"
        | "snapshot_taken" | "snapshot_restored"
        | "broker_status" | "ce_status",
  "id": "u-1",
  "data": { /* kind-specific */ }
}
```

The same events are appended (without the `chat_token` ones — too noisy) to `%LOCALAPPDATA%\CEGM\activity\<session_id>.jsonl` for replay.

## Error envelope

```jsonc
{
  "code": "ce_not_attached" | "preview_not_found" | "preview_already_committed" |
          "snapshot_not_found" | "address_invalid" | "upstream_error" |
          "config_invalid" | "validation_failed",
  "message": "human-readable",
  "data": { /* tool-specific */ }
}
```

`upstream_error` is reserved for failures from the proxied miscusi-peek child; the original error from upstream is included in `data.upstream`.

## Versioning

The broker handshake exchanges `cegm_version`, `proxy_version` (the pinned miscusi-peek commit), and a `tools_extras_version` hash. External MCP clients can read these via the standard `tools/list` `_meta` field.
