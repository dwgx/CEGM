/**
 * @file Bottom Console — shows tool call/output/error log with level-colored lines.
 */

const MAX_LINES = 500;
let _lines = 0;

function body() { return document.getElementById("console-body"); }

function timeShort(iso) {
  const m = iso?.match?.(/T(\d\d:\d\d:\d\d)/);
  return m ? m[1] : new Date().toISOString().slice(11, 19);
}

function levelForKind(kind) {
  if (!kind) return "info";
  if (kind.includes("error")) return "error";
  if (kind.includes("warn")) return "warn";
  if (kind.startsWith("tool_")) return "tool";
  if (kind === "scan_started" || kind === "watch_frozen" || kind === "broker_status") return "success";
  return "info";
}

function formatEvent(evt) {
  const ts = timeShort(evt.ts);
  const kind = evt.kind || "event";
  const data = evt.data || {};
  switch (kind) {
    case "tool_called": return `${ts} ▶ ${data.name || "?"}(${JSON.stringify(data.arguments || {})})`;
    case "tool_result": return `${ts} ✓ ${data.name || "?"} ok`;
    case "tool_error":  return `${ts} ✗ ${data.name || "?"} ${data.error || ""}`;
    case "chat_user":   return `${ts} 👤 ${(data.content || "").slice(0, 200)}`;
    case "chat_assistant": return `${ts} 🤖 ${(data.content || "").slice(0, 200)}`;
    case "scan_started": return `${ts} ◎ scan "${data.value}" vt=${data.vt} → ${data.count} hits`;
    case "scan_narrowed": return `${ts} ◎ narrowed → ${data.count} hits`;
    case "watch_added": return `${ts} ⌖ watch +${data.address} (${data.vt}) ${data.label || ""}`;
    case "watch_frozen": return `${ts} ❄ frozen ${data.address} at ${data.freeze_value}`;
    case "watch_unfrozen": return `${ts} 🧊 unfrozen ${data.address}`;
    case "watch_update": return null; // too noisy
    case "broker_status": return `${ts} ⚡ broker v${data.version}, proxy=${data.proxy_available}, ${data.proxy_tool_count} tools`;
    default: return `${ts} [${kind}] ${JSON.stringify(data).slice(0, 200)}`;
  }
}

export function appendConsoleLine(evt) {
  const b = body(); if (!b) return;
  const text = formatEvent(evt);
  if (!text) return;
  const level = levelForKind(evt.kind);
  const div = document.createElement("div");
  div.className = `console-line ${level}`;
  div.textContent = text;
  b.append(div);
  if (_lines++ > MAX_LINES) { b.firstElementChild?.remove(); _lines--; }
  b.scrollTop = b.scrollHeight;
}

export function clearConsole() {
  const b = body(); if (b) b.innerHTML = "";
  _lines = 0;
}
