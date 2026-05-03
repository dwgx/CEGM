# ADR-0003: File-based IPC between CE plugin and broker for MVP

- **Status:** **superseded by [ADR-0004](0004-build-on-miscusi-peek.md)** (2026-05-03)
- **Date:** 2026-05-03 (accepted) → 2026-05-03 (superseded)
- **Deciders:** dwgx (project owner)

> **Superseded note (2026-05-03):** Late on 2026-05-03 we discovered miscusi-peek/cheatengine-mcp-bridge already provides a working CE↔Python IPC via named pipes (`\\.\pipe\CE_MCP_Bridge_v99`). ADR-0004 pivots CEGM to vendor that project as our backend, which makes the file-IPC design here unnecessary. The original analysis below is preserved as a historical record of why building our own IPC was attractive when we believed we'd implement the full backend ourselves.

---

## Original ADR (now historical)

## Context

The CE Lua plugin and the Python broker run as separate processes and need to exchange JSON-RPC messages in both directions:

- **Broker → Plugin**: tool execution requests (`scan_first(...)`, `memory_read(...)`)
- **Plugin → Broker**: tool execution responses + status updates
- **Broker → Plugin**: audit / log events for the activity feed

CE 7.5's Lua runtime imposes hard constraints (see [research/ce-lua-api.md](../research/ce-lua-api.md) §4):

- **No bundled LuaSocket.** Standard luarocks builds crash-load against CE's patched `lua53-32/64.dll`. Shipping our own compiled `socket.core.dll` requires a build pipeline against CE headers and re-rebuild on every CE update.
- **`io.popen` is unidirectional in standard Lua.** A child process can be either written to or read from, not both, without a custom DLL helper.
- **Custom DLLs require parallel 32-bit and 64-bit builds.** CE ships separate `cheatengine-i386.exe` and `cheatengine-x86_64.exe` with separate `lua_modules` paths.

So none of {direct TCP from Lua, bidirectional stdio from Lua, custom DLL helper} are zero-cost. Each adds a build artifact or a fragile dependency to the plugin.

## Decision

**MVP uses file-based IPC** under `%LOCALAPPDATA%\CEGM\rpc\`:

- `requests.jsonl` — broker appends JSON-RPC request envelopes; plugin tails by polling on a `createTimer` (~50–100 ms interval).
- `responses.jsonl` — plugin appends response envelopes; broker tails via `watchdog` or a polling task.
- `events.jsonl` — broker appends audit/log events; plugin tails for the activity feed display. Same file as the broker's structured log output.

Each line is a single JSON object with at minimum `id` (UUID), `ts` (ISO-8601), `kind` (`request` / `response` / `event`). Files are append-only; a rotation job (or per-session subdirectory) keeps them bounded.

## Consequences

### Positives

- **Zero new build artifacts.** The plugin remains pure Lua + bundled `dkjson.lua`. No `*.dll` to compile or maintain across CE bitnesses and version bumps.
- **Crash-resilient.** Pending requests survive a broker or CE crash; on restart the surviving process can replay from the file (or skip ahead by `id`).
- **Trivial to debug.** `tail -f %LOCALAPPDATA%\CEGM\rpc\events.jsonl` shows everything that's happening, by humans or by future tooling, without any IPC inspector.
- **Doubles as the audit log.** The broker is going to write the activity feed as JSONL anyway (see [research/mcp-python-sdk.md](../research/mcp-python-sdk.md) §8). Reusing it as one of the IPC channels saves a separate transport.
- **Filesystem watching is well-supported in Python.** `watchdog` on Windows uses `ReadDirectoryChangesW` and is reliable. Polling with a small sleep is also fine for our latency budget.

### Negatives

- **Latency floor ≈ poll interval.** A 100 ms timer means tools finish 100 ms slower in the worst case. Acceptable for human-paced workflow; a memory scan takes seconds anyway.
- **Cross-process file locking on Windows.** Append writes on Windows are atomic up to ~512 bytes (`O_APPEND`-equivalent). Each JSONL line must fit in that budget — large payloads (full scan dumps) go in a separate file referenced by URI in the response, not inline.
- **Cleanup discipline.** Files grow without bound unless rotated. We rotate per-session: `rpc/<session_id>/requests.jsonl` etc., with a TTL sweeper.
- **No back-pressure signal.** A slow consumer just gets behind. We add a watermark line and a "broker overloaded" event when the lag exceeds a threshold.

### Reversibility

The protocol layer (`{id, kind, method, params, result, error}`) is transport-agnostic. If file IPC ever becomes the bottleneck we swap to:

1. **Custom DLL helper.** A ~200-line C module that does named-pipe IPC, compiled against CE headers, shipped per-bitness. Same JSON envelopes, half the latency.
2. **Pre-compiled LuaSocket.** Trade build complexity for TCP simplicity once we've absorbed CE's quirks.
3. **stdio with a side-pipe DLL.** Custom DLL only does the bidirectional pipe handshake; everything else is stdio.

None of these require changes to the broker side or the message schema, just to `plugin/lib/bridge.lua`.

## Alternatives considered

- **Direct TCP via shipped LuaSocket DLL.** Rejected for MVP. Maintenance cost of two `socket.core.dll` builds tied to CE's lua53 ABI is too high before we've proved the project. Reconsider in Phase 5+.
- **Bidirectional stdio via custom DLL.** Same maintenance cost, marginal latency win, harder to debug than files. Rejected for MVP.
- **WinAPI WSA via `executeCodeLocal` / FFI.** Hairy, hard to test, no community precedent for this exact pattern in CE plugins. Rejected.
- **Named pipes via `CreateFileW` from FFI.** Cleaner than WSA but still needs FFI scaffolding. Reconsider as the upgrade path if Phase 1 latency is unacceptable.
- **Shared memory.** Overkill; tooling-heavy; no obvious latency win at human speeds.
