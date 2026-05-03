--[[
  log.lua — JSONL logger for the plugin side.

  Schema-compatible with the broker's logs (`ts`, `level`, `event`, plus
  arbitrary kv fields). Writes to plugin.log; safe to call from any thread.
]]

local paths = require("paths")
local dkjson = require("dkjson")

local M = {}

---Format an ISO-8601 UTC timestamp with millisecond precision.
---@return string
local function iso_now()
  -- Lua 5.3's `os.date` doesn't natively give us milliseconds. CE ships with
  -- `getTickCount` for that; if absent fall back to seconds-only.
  local s = os.date("!%Y-%m-%dT%H:%M:%S")
  local ms = 0
  if type(_G.getTickCount) == "function" then
    ms = _G.getTickCount() % 1000
  end
  return string.format("%s.%03dZ", s, ms)
end

---Append a single JSONL line.
---@param level string
---@param event string
---@param fields table|nil
local function emit(level, event, fields)
  local payload = fields and { } or { }
  if fields then
    for k, v in pairs(fields) do payload[k] = v end
  end
  payload.ts = iso_now()
  payload.level = level
  payload.logger = "plugin"
  payload.event = event

  local line = dkjson.encode(payload, { indent = false })
  local fh, err = io.open(paths.plugin_log_path(), "a")
  if not fh then
    -- Last-ditch: write to CE's main message panel if available.
    if type(_G.print) == "function" then _G.print("[cegm log open failed] " .. tostring(err)) end
    return
  end
  fh:write(line, "\n")
  fh:close()
end

function M.debug(event, fields) emit("debug", event, fields) end
function M.info(event, fields)  emit("info",  event, fields) end
function M.warn(event, fields)  emit("warn",  event, fields) end
function M.error(event, fields) emit("error", event, fields) end

return M
