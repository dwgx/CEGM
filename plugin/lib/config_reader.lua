--[[
  config_reader.lua — Read %LOCALAPPDATA%\CEGM\config.json into a Lua table.

  The broker is the single source of truth for runtime config. The Lua
  plugin doesn't write config — the dashboard does, via PUT /api/config.
  We only consume what's there. If the file doesn't exist yet (very
  first CE startup before the dashboard has been opened), we hand back
  the same defaults the broker would use.
]]

local paths  = require("paths")
local dkjson = require("dkjson")

local M = {}

---Defaults that match cegm_broker.config defaults. Keep in sync.
local DEFAULTS = {
  ui = { show_status_form = false },
  server = { host = "127.0.0.1", port = 27077 },
}

---Shallow-merge ``patch`` over ``base`` (used for top-level sections).
local function merge(base, patch)
  local out = {}
  for k, v in pairs(base) do out[k] = v end
  if type(patch) == "table" then
    for k, v in pairs(patch) do out[k] = v end
  end
  return out
end

---Load + parse the JSON config. Always returns a table; missing fields
---fall back to the defaults declared above so callers never have to
---nil-check.
---@return table
function M.load()
  local fh = io.open(paths.config_path(), "r")
  if not fh then return DEFAULTS end
  local raw = fh:read("*a") or ""
  fh:close()
  if raw == "" then return DEFAULTS end

  local parsed = dkjson.decode(raw)
  if type(parsed) ~= "table" then return DEFAULTS end

  return {
    ui     = merge(DEFAULTS.ui,     parsed.ui),
    server = merge(DEFAULTS.server, parsed.server),
  }
end

return M
