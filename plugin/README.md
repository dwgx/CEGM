# plugin/ — Cheat Engine Lua autorun bundle

The CE-side of CEGM. Two scripts ship into `<CE>/autorun/CEGM/`:

1. **`cegm.lua`** (ours) — minimal shim. Spawns the broker on CE startup, shows a small status form with an "Open Dashboard" button, and gets out of the way. Strictly main-thread, no scans, no blocking.
2. **`ce_mcp_bridge.lua`** (vendored from [miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge), MIT) — exposes the CE Lua API to the broker via a named pipe. Copied at install time from `vendor/cheatengine-mcp-bridge/MCP_Server/ce_mcp_bridge.lua`.

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for the full picture and [docs/decisions/0004-build-on-miscusi-peek.md](../docs/decisions/0004-build-on-miscusi-peek.md) for why we vendor instead of reimplementing.

## Layout (Phase 1)

```
plugin/
├── cegm.lua                 # autorun entry — spawns broker, opens status form
├── lib/
│   ├── bridge_spawn.lua     # detached child-process launch via os.execute
│   ├── ui.lua               # floating status form (port, broker pid, "Open Dashboard")
│   ├── port_probe.lua       # checks if 127.0.0.1:27077 is bound (avoids double-spawn)
│   ├── log.lua              # appends to %LOCALAPPDATA%\CEGM\logs\plugin.log
│   └── dkjson.lua           # pure-Lua JSON, MIT (vendored)
└── README.md                # this file
```

## Threading

CE Lua is single-threaded on the main UI thread. **Never** block here. miscusi-peek's `ce_mcp_bridge.lua` already handles `createThread` / `synchronize` for the heavy stuff (memory scans, debug events). Our `cegm.lua` only does:

- Read `%LOCALAPPDATA%\CEGM\config.json`
- Probe whether port 27077 is already bound (≤ 50 ms socket connect attempt via the `package.cpath`-loadable winsock helper, or via a port-file marker the broker writes — TBD in implementation)
- `os.execute('start /B "" cegm-broker --port 27077 --parent-pid <CE_PID>')` to spawn detached
- Build a small floating form via `createForm` + `createLabel` + `createButton`

## Install (manual, until the Phase 5 installer)

1. Locate the Cheat Engine install directory (typically `C:\Program Files\Cheat Engine 7.5\`).
2. Create `<CE>\autorun\CEGM\`.
3. Copy `plugin\cegm.lua` and `plugin\lib\` into it.
4. Copy `vendor\cheatengine-mcp-bridge\MCP_Server\ce_mcp_bridge.lua` into the same `<CE>\autorun\CEGM\` directory.
5. Install the broker: `uv tool install cegm-broker` (Phase 1 publishes to PyPI).
6. Launch CE. The CEGM status form should appear and show "broker running on port 27077".

## 32-bit vs 64-bit

CE ships separate `cheatengine-i386.exe` and `cheatengine-x86_64.exe` with separate `autorun/` execution. Plugin auto-detects via `targetIs64Bit()` after the user attaches; broker handles both bitnesses transparently because miscusi-peek's bridge already does.

## Status

Skeleton only — see [docs/ROADMAP.md](../docs/ROADMAP.md) Phase 1.
