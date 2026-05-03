--[[
  spawn.lua — Launch `cegm-broker.exe` detached from Cheat Engine.

  Uses `cmd /c start` so the broker survives Lua's call returning and
  doesn't keep an open pipe to CE's main thread. The broker's
  `--parent-pid` argument is what closes the loop — it polls that PID and
  exits when CE goes away (see broker/src/cegm_broker/parent_watch.py).
]]

local M = {}

---@class SpawnArgs
---@field port integer
---@field parent_pid integer
---@field log_level string|nil

local VALID_LOG_LEVELS = {
  debug = true, info = true, warning = true, error = true, critical = true,
}

---Detach `cegm-broker` with the given arguments. Fire-and-forget; we do
---not capture stdout/stderr (broker logs to its own JSONL file).
---
---All arguments are coerced to safe forms before being interpolated into
---the shell command — `port` and `parent_pid` are forced to integers via
---`%d` formatting, and `log_level` is whitelisted against the broker's
---known set so a malicious caller can't smuggle shell metacharacters in.
---
---@param args SpawnArgs
---@return boolean ok, string|nil err
function M.detached_broker(args)
  if type(args) ~= "table" then return false, "args must be a table" end
  local port = math.floor(tonumber(args.port) or 27077)
  local parent_pid = math.floor(tonumber(args.parent_pid) or 0)
  local log_level = args.log_level
  if not (type(log_level) == "string" and VALID_LOG_LEVELS[log_level]) then
    log_level = "info"
  end

  -- `start "" /B` runs without a new console window and without title
  -- shadowing. The empty title arg ("") is required to disambiguate
  -- start's title vs. command parsing.
  local cmd = string.format(
    'cmd /c start "" /B cegm-broker --port %d --parent-pid %d --log-level %s',
    port, parent_pid, log_level
  )
  local ok, _, code = os.execute(cmd)
  if ok == true then return true end
  if ok == nil and code == 0 then return true end
  return false, ("cmd exited with code " .. tostring(code))
end

---Open the user's default browser at the given URL (used by the
---"Open Dashboard" button).
---@param url string
function M.open_browser(url)
  os.execute(string.format('cmd /c start "" "%s"', url))
end

return M
