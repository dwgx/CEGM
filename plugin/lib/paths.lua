--[[
  paths.lua — Resolve filesystem paths the CEGM plugin uses at runtime.

  Mirrors `cegm_broker._paths` so plugin and broker agree on where state
  lives. All persistent state sits under %LOCALAPPDATA%\CEGM\.
]]

local M = {}

---Return %LOCALAPPDATA%\CEGM (or a sensible fallback for development).
---@return string
function M.data_root()
  local override = os.getenv("CEGM_DATA_DIR")
  if override and override ~= "" then return override end
  local local_appdata = os.getenv("LOCALAPPDATA")
  if local_appdata and local_appdata ~= "" then
    return local_appdata .. "\\CEGM"
  end
  -- Fallback (non-Windows dev box).
  return (os.getenv("HOME") or ".") .. "/.local/share/CEGM"
end

---Path of the JSON config file shared with the broker.
---@return string
function M.config_path() return M.data_root() .. "\\config.json" end

---Path of the plugin-side log file (kept separate from the broker's).
---@return string
function M.plugin_log_path() return M.data_root() .. "\\logs\\plugin.log" end

---Path of the marker file the broker writes once it has bound a port.
---Plugin polls this for "is broker up?".
---@return string
function M.broker_pid_path() return M.data_root() .. "\\broker.pid" end

---Create %LOCALAPPDATA%\CEGM\ and the logs/ subdirectory if missing.
function M.ensure_data_root()
  local root = M.data_root()
  -- `mkdir` on Windows ignores existing dirs but errors with garbage if path
  -- has spaces unquoted. Use cmd /c to handle redirect of stderr safely.
  os.execute(string.format('cmd /c mkdir "%s" 2>nul', root))
  os.execute(string.format('cmd /c mkdir "%s\\logs" 2>nul', root))
end

return M
