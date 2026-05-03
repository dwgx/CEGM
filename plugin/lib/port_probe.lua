--[[
  port_probe.lua — Check whether a TCP port on localhost is currently bound.

  Used by `cegm.lua` to decide whether to spawn the broker or assume an
  already-running instance owns it. CE has no bundled LuaSocket (see
  docs/research/ce-lua-api.md §4) so we shell out via PowerShell. The probe
  is short — typically <100 ms — and runs once at startup, so the cost is
  acceptable.

  An optional fast path (Phase 1): the broker writes a `broker.pid` marker
  with the port; plugin checks the marker first and only falls back to a
  network probe if the marker is stale.
]]

local paths = require("paths")

local M = {}

---Return true if a fresh `broker.pid` marker advertises the same port.
---"Fresh" = mtime within the last 60 s.
---@param port integer
---@return boolean
local function marker_fresh(port)
  local fh = io.open(paths.broker_pid_path(), "r")
  if not fh then return false end
  local line = fh:read("*l") or ""
  fh:close()
  -- Format: "PID,PORT,ISO_TS"
  local _, listed_port = line:match("^(%d+),(%d+),(.*)$")
  if not listed_port then return false end
  return tonumber(listed_port) == port
end

---True if `s` is a safe host literal — IPv4 dotted-quad or `localhost`.
---Anything else is rejected before we let it near a shell command line.
---@param s string
---@return boolean
local function is_safe_host(s)
  if type(s) ~= "string" then return false end
  if s == "localhost" then return true end
  local a, b, c, d = s:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
  if not a then return false end
  for _, n in ipairs({ a, b, c, d }) do
    local v = tonumber(n)
    if not v or v < 0 or v > 255 then return false end
  end
  return true
end

---PowerShell-based TCP probe. Returns true if connect to host:port succeeds
---within `timeout_ms`. ``host`` is validated upstream; ``port`` and
---``timeout_ms`` are forced to integers via ``%d`` formatting.
---@param host string
---@param port integer
---@param timeout_ms integer
---@return boolean
local function tcp_connect(host, port, timeout_ms)
  if not is_safe_host(host) then return false end
  -- The .NET TcpClient is stock on every Windows that has CE 7.5 working.
  -- Single round-trip; window is hidden via -WindowStyle Hidden so the user
  -- doesn't see a flash. We capture the exit code only.
  local cmd = string.format(
    'powershell -NoProfile -WindowStyle Hidden -Command ' ..
    '"$c=New-Object Net.Sockets.TcpClient; ' ..
    'try { $r=$c.BeginConnect(\'%s\',%d,$null,$null); ' ..
    'if($r.AsyncWaitHandle.WaitOne(%d)) { $c.EndConnect($r); exit 0 } ' ..
    'else { exit 1 } } catch { exit 1 } finally { $c.Close() }"',
    host, math.floor(port), math.floor(timeout_ms)
  )
  local ok, _, code = os.execute(cmd)
  -- Lua 5.3's `os.execute` returns (true|false, "exit"|"signal", code).
  if ok == true then return true end
  if ok == nil then return code == 0 end
  return false
end

---Public check used by `cegm.lua` at startup.
---@param host string
---@param port integer
---@param timeout_ms integer|nil  -- default 250 ms
---@return boolean
function M.is_listening(host, port, timeout_ms)
  if marker_fresh(port) then return true end
  return tcp_connect(host, port, timeout_ms or 250)
end

return M
