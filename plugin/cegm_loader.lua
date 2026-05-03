--[[
  cegm_loader.lua — top-level autorun bootstrap for CEGM.

  CE's autorun mechanism executes top-level *.lua files only; subdirectories
  are not recursed. This 14-line loader is the single file we drop into
  <CE>/autorun/, and it dofile()s the real scripts from <CE>/autorun/CEGM/:

      cegm_loader.lua   (this file)
      CEGM/
        cegm.lua            — our shim (status form, broker spawn)
        ce_mcp_bridge.lua   — miscusi-peek named-pipe MCP bridge (vendored)
        lib/                — our Lua modules (paths, log, ui, …, dkjson)

  Order matters: the bridge starts first so the named pipe is listening
  before any external broker tries to attach.

  License: GPL-2.0-only.
]]

local function script_dir()
  local src = debug.getinfo(1, "S").source
  if src:sub(1, 1) == "@" then src = src:sub(2) end
  return src:gsub("[^/\\]+$", "")
end

local CEGM_DIR = script_dir() .. "CEGM" .. package.config:sub(1, 1)

local ok_bridge, err_bridge = pcall(dofile, CEGM_DIR .. "ce_mcp_bridge.lua")
if not ok_bridge then
  print("[cegm_loader] bridge failed: " .. tostring(err_bridge))
end

local ok_shim, err_shim = pcall(dofile, CEGM_DIR .. "cegm.lua")
if not ok_shim then
  print("[cegm_loader] shim failed: " .. tostring(err_shim))
end
