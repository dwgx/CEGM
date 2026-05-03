--[[
  cegm_loader.lua — top-level autorun bootstrap for CEGM.

  CE's autorun mechanism executes top-level *.lua files only; subdirectories
  are not recursed. This loader is the single file we drop into
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

-- ── suppress CE Lua-engine window auto-popup ─────────────────────────
-- miscusi-peek's bridge writes every status line via ``print("[MCP v..."
-- .. msg)``, which CE routes to its Lua engine output window and pops
-- the window open as soon as anything lands there. We don't want that
-- window appearing every CE startup (and every time a tool runs). So
-- we install a thin wrapper around ``print`` that:
--   • siphons "[MCP v..." prefixed lines to a rolling file under
--     %LOCALAPPDATA%\CEGM\logs\bridge.log
--   • passes everything else through to CE's real print, so a user
--     typing print(...) into the Lua engine console still works.
local _orig_print = print

local function bridge_log_path()
  local appdata = os.getenv("LOCALAPPDATA")
  if appdata and #appdata > 0 then
    return appdata .. "\\CEGM\\logs\\bridge.log"
  end
  return "cegm_bridge.log"
end

local LOG_PATH = bridge_log_path()
-- Note: no ``mkdir`` shell-out here on purpose. Spawning ``cmd /c mkdir``
-- briefly flashes a console window on Windows even with stderr redirected.
-- If the directory doesn't exist, ``io.open`` below silently fails — the
-- broker creates the directory on its own first write anyway.

_G.print = function(...)
  local n = select("#", ...)
  local pieces = {}
  for i = 1, n do pieces[i] = tostring((select(i, ...))) end
  local line = table.concat(pieces, "\t")
  if line:sub(1, 5) == "[MCP " or line:sub(1, 6) == "[cegm_" then
    local fh = io.open(LOG_PATH, "a")
    if fh then
      fh:write(os.date("!%Y-%m-%dT%H:%M:%SZ"), " ", line, "\n")
      fh:close()
    end
    return
  end
  return _orig_print(...)
end

-- ── load the real scripts ────────────────────────────────────────────
local ok_bridge, err_bridge = pcall(dofile, CEGM_DIR .. "ce_mcp_bridge.lua")
if not ok_bridge then
  print("[cegm_loader] bridge failed: " .. tostring(err_bridge))
end

local ok_shim, err_shim = pcall(dofile, CEGM_DIR .. "cegm.lua")
if not ok_shim then
  print("[cegm_loader] shim failed: " .. tostring(err_shim))
end
