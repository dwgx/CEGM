# plugin/native/ — CEGM Cheat Engine plugin DLL

A minimal C plugin that registers CEGM in CE's **Settings → Plugins** list and adds an **Open CEGM Dashboard** entry to the main menu. The DLL itself is small — the real work happens in the autorun Lua scripts and the Python broker; this is just the front-door so CEGM appears as a real plugin and not just a pile of autorun scripts.

## Build

You need Visual Studio 2022 (or 2019) with the **Desktop development with C++** workload installed. The `build.ps1` script auto-detects MSVC via `vswhere` and your CE install via the Start Menu shortcut.

```powershell
# from anywhere
powershell -ExecutionPolicy Bypass -File plugin\native\build.ps1

# build x64 and copy to <CE>\plugins\ in one go
powershell -ExecutionPolicy Bypass -File plugin\native\build.ps1 -InstallToCE

# explicit paths
powershell -ExecutionPolicy Bypass -File plugin\native\build.ps1 `
  -CEDir "D:\Debugger\Cheat Engine" -Arch amd64 -InstallToCE

# x86 build (for 32-bit CE)
powershell -ExecutionPolicy Bypass -File plugin\native\build.ps1 -Arch x86 -InstallToCE
```

Output lands in `plugin\native\dist\CEGM-x64.dll` (or `CEGM-x86.dll`).

## Install (manual)

1. Copy `CEGM-x64.dll` into `<CE>\plugins\`.
2. Open Cheat Engine → **设置** (Settings) → **插件** (Plugins).
3. Click **添加新项** (Add new item) and pick the DLL.
4. Tick its checkbox, click **确定** (OK), restart CE.
5. After restart, **CEGM (CheatEngineGM)** shows in the plugin list and an **Open CEGM Dashboard** entry appears in the main menu.

The dashboard is served by the auto-spawned Python broker at `http://127.0.0.1:27077/`.

## Bitness

CE 7.5 ships separate `cheatengine-i386.exe` and `cheatengine-x86_64.exe` binaries. Each loads only DLLs of matching bitness. The launcher (`Cheat Engine.exe`) picks one based on settings; build the matching variant. Most modern installs use x64.

## What this plugin does NOT do

It does not implement the MCP server, the named-pipe bridge, or any memory operations directly. Those live in:

- `vendor/cheatengine-mcp-bridge/MCP_Server/ce_mcp_bridge.lua` (named-pipe bridge, autorun)
- `plugin/cegm_loader.lua` + `plugin/cegm.lua` (status form, broker spawn, autorun)
- `broker/` (Python — MCP HTTP server, dashboard, LLM client)

If you want a richer in-CE UI (e.g. dock a panel into the main window), this is the file to extend — see [docs/research/ce-lua-api.md](../../docs/research/ce-lua-api.md) §3 for the docking pattern and the SDK header `<CE>\plugins\cepluginsdk.h` for the available callback types.
