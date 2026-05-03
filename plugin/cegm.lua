--[[
  cegm.lua — CheatEngineGM plugin entry point (Cheat Engine 7.5+ autorun)

  Loaded automatically by Cheat Engine when this file lives in
    <CE>/autorun/CEGM/cegm.lua

  Responsibilities (intentionally minimal — heavy lifting is in the broker):
    1. Probe whether the CEGM broker is already running.
    2. If not, spawn `cegm-broker.exe` detached, passing CE's PID so the broker
       exits when CE exits.
    3. Open a small floating status form with an "Open Dashboard" button that
       launches the user's default browser at http://127.0.0.1:<port>/.

  This file MUST stay strictly main-thread. No memory scans here. No blocking
  network calls. No `sleep`. The broker does all of that.

  Vendored alongside this script (copied at install time):
    ce_mcp_bridge.lua  — from miscusi-peek/cheatengine-mcp-bridge (MIT)
                          Provides the actual CE↔Python named-pipe bridge.

  License: GPL-2.0-only (same as repo). Loads `dkjson` (MIT, vendored).
]]

local SCRIPT_DIR = (function()
  local src = debug.getinfo(1, "S").source
  if src:sub(1, 1) == "@" then src = src:sub(2) end
  return src:gsub("[^/\\]+$", "")
end)()

-- Make plugin/lib/ requireable.
package.path = SCRIPT_DIR .. "lib/?.lua;" .. package.path

local log           = require("log")
local ui            = require("ui")
local config_reader = require("config_reader")

local DEFAULT_PORT = 27077

---@class CegmState
---@field port integer
---@field broker_running boolean
---@field broker_pid integer|nil
---@field last_check_ts integer  -- os.time() of last health probe

---Pick the broker port for this session, honoring any override in
---``config.json``.
---@param cfg table -- result of config_reader.load()
---@return integer
local function chosen_port(cfg)
  local p = cfg.server and tonumber(cfg.server.port)
  if p and p > 0 and p <= 65535 then return math.floor(p) end
  return DEFAULT_PORT
end


---Initialize CEGM state. The Lua plugin no longer spawns the broker —
---that responsibility belongs to either:
---  1. The native C plugin (``plugin/native/CEGM-x64.dll``), which can
---     ``CreateProcessW`` ``cegm-broker.exe`` with ``CREATE_NO_WINDOW``
---     once it's resolved on PATH; or
---  2. The user, running ``cegm-broker --port 27077`` manually.
---Spawning from Lua via ``os.execute`` always goes through ``cmd.exe``
---and pops a "command not found" dialog when the binary isn't on PATH
---(common when the user is iterating with ``uv run`` rather than
---``uv tool install``). Better to do nothing and let the broker reach
---the user via one of the two paths above.
---@return CegmState, table
local function bootstrap()
  local cfg = config_reader.load()
  local port = chosen_port(cfg)
  log.info("cegm.bootstrap_started", {
    port = port,
    show_status_form = cfg.ui.show_status_form,
  })

  ---@type CegmState
  local state = {
    port = port,
    broker_running = false,  -- unknown; we don't probe (would require shell-out)
    broker_pid = nil,
    last_check_ts = os.time(),
  }
  return state, cfg
end

-- Defer GUI work to the next event-loop tick (recommended pattern from
-- Dark Byte's autorun guidance — see docs/research/ce-lua-api.md §1).
local boot_timer = createTimer(getMainForm() or nil, false)
boot_timer.Interval = 1
boot_timer.OnTimer = function(self)
  self.destroy()
  local state, cfg = bootstrap()
  if cfg.ui.show_status_form then
    ui.show_status_form(state)
  else
    log.info("cegm.status_form_suppressed")
  end
end
boot_timer.Enabled = true
