--[[
  ui.lua — Floating status form for the CEGM plugin.

  CE Lua exposes only top-level forms (no docked panels — see
  docs/research/ce-lua-api.md §3). This is a small always-on-top window
  the user can move out of the way; the real UX lives in the browser
  dashboard at http://127.0.0.1:<port>/.

  Layout:
    +----------------------------------------+
    |  CEGM 0.1.0a1                  [- □ x] |
    +----------------------------------------+
    |  Broker status: running on 27077       |
    |  PID: 12345                            |
    |                                        |
    |  [  Open Dashboard  ]   [  Reload  ]   |
    +----------------------------------------+
]]

local spawn = require("spawn")

local M = {}

local FORM_WIDTH  = 360
local FORM_HEIGHT = 160

---Build and show the status form for the given state.
---@param state CegmState
---@return userdata form
function M.show_status_form(state)
  local form = createForm(false)
  form.Caption = "CEGM 0.1.0a1"
  form.Width = FORM_WIDTH
  form.Height = FORM_HEIGHT
  form.BorderStyle = "bsSingle"
  form.Position = "poDesktopCenter"

  local lblStatus = createLabel(form)
  lblStatus.Left = 12
  lblStatus.Top = 14
  lblStatus.Caption = "Broker status: " ..
    (state.broker_running and "already running" or "spawning…")

  local lblPort = createLabel(form)
  lblPort.Left = 12
  lblPort.Top = 36
  lblPort.Caption = string.format("Endpoint: http://127.0.0.1:%d/", state.port)

  local lblHint = createLabel(form)
  lblHint.Left = 12
  lblHint.Top = 58
  lblHint.Caption =
    "External MCP clients (Claude Desktop, Cursor, Codex)\n" ..
    "connect to /mcp on this host."

  local btnOpen = createButton(form)
  btnOpen.Left = 12
  btnOpen.Top = 110
  btnOpen.Width = 150
  btnOpen.Caption = "Open Dashboard"
  btnOpen.OnClick = function()
    spawn.open_browser(string.format("http://127.0.0.1:%d/", state.port))
  end

  local btnReload = createButton(form)
  btnReload.Left = 180
  btnReload.Top = 110
  btnReload.Width = 150
  btnReload.Caption = "Reload Plugin"
  btnReload.OnClick = function()
    -- Phase 1: re-execute autorun. For now leave a hint.
    showMessage("Reload not yet implemented (Phase 1).")
  end

  form.show()
  return form
end

return M
