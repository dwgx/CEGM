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

local paths         = require("paths")
local log           = require("log")
local port_probe    = require("port_probe")
local spawn         = require("spawn")
local ui            = require("ui")
local config_reader = require("config_reader")

local DEFAULT_PORT = 27077
local PROBE_TIMEOUT_MS = 3000  -- give broker up to 3s to start binding

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

---Get our own (Cheat Engine's) PID for the parent-watch handshake.
---@return integer
local function our_pid()
  -- CE exposes this via the global `getCEProcessID()` in 7.5+; fall back to
  -- whatever's available on older builds.
  if type(_G.getCEProcessID) == "function" then
    return _G.getCEProcessID()
  end
  return 0
end

---Initialize CEGM state and run the spawn flow.
---@return CegmState, table
local function bootstrap()
  paths.ensure_data_root()
  local cfg = config_reader.load()
  local port = chosen_port(cfg)
  log.info("cegm.bootstrap_started", {
    port = port,
    show_status_form = cfg.ui.show_status_form,
  })

  ---@type CegmState
  local state = {
    port = port,
    broker_running = false,
    broker_pid = nil,
    last_check_ts = os.time(),
  }

  if port_probe.is_listening("127.0.0.1", state.port, 250) then
    state.broker_running = true
    log.info("cegm.broker_already_running", { port = state.port })
  else
    local ok, err = spawn.detached_broker({
      port = state.port,
      parent_pid = our_pid(),
    })
    if not ok then
      log.error("cegm.spawn_failed", { err = tostring(err) })
    else
      log.info("cegm.broker_spawned", { port = state.port, parent_pid = our_pid() })
    end
  end

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
