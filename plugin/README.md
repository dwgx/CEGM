# plugin/ — Cheat Engine Lua plugin

The CE-side of CEGM. Loaded by Cheat Engine's autorun mechanism; talks to the Python broker via JSONL files under `%LOCALAPPDATA%\CEGM\rpc\`. See [ADR-0003](../docs/decisions/0003-ipc-mechanism.md) for why files instead of sockets.

## Layout (planned, Phase 1)

```
plugin/
├── cegm.lua              # autorun entry — sets up package.path, loads lib/*, opens form
├── lib/
│   ├── bridge.lua        # JSONL file IPC: tail requests.jsonl, append responses.jsonl
│   ├── ui.lua            # floating form: status row + activity feed (tail of events.jsonl)
│   ├── tools.lua         # CE operation handlers (scan_first, memory_read, ...)
│   ├── workers.lua       # createThread wrappers for blocking ops, synchronize() helpers
│   ├── log.lua           # parse events.jsonl lines into UI rows
│   └── dkjson.lua        # vendored pure-Lua JSON (https://dkolf.de/dkjson-lua/)
└── README.md             # this file
```

CE has no bundled JSON or socket libraries. We vendor `dkjson.lua` (pure Lua, MIT, single file). No DLLs to ship.

## Install (manual, until Phase 5 installer)

1. Locate the Cheat Engine install directory (typically `C:\Program Files\Cheat Engine 7.5\`).
2. Copy the entire `plugin/` directory into `<CE>/autorun/CEGM/` (create the `CEGM` subdirectory).
3. Ensure `<CE>/autorun/CEGM/cegm.lua` exists. CE will execute it on next startup.
4. Start the broker (`uvx cegm-broker` or `uv tool run cegm-broker`).
5. Launch CE; the CEGM panel should appear and show "broker connected".

## Threading

CE's Lua runs on the main UI thread. **Never** block here — `MemScan:waitTillDone()`, `AOBScan` on the full address space, `sleep`, large `readBytes` with table return, or `os.execute` (sync) all freeze the GUI.

Pattern: a single `createTimer` on the main thread polls `requests.jsonl` (~50–100 ms). When a request arrives, dispatch it into a `createThread` worker that runs the CE operation, then uses `synchronize(fn)` to safely write the response back and append a UI row.

The plugin's job is intentionally minimal: render UI, execute CE operations the broker requests, tail the broker's log file. All LLM / MCP / heavy work lives in the Python broker.

## 32-bit vs 64-bit

CE ships separate `cheatengine-i386.exe` and `cheatengine-x86_64.exe` with separate `autorun/` runs. Plugin must detect bitness via `getProcesslist`'s host process or `targetIs64Bit()` and adapt scan vartypes accordingly (e.g. `vtQword` makes no sense in a 32-bit-only target).

## Status

Skeleton only — no Lua files yet. See [docs/ROADMAP.md](../docs/ROADMAP.md) Phase 1.
