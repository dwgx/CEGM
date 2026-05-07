/**
 * @file Timeline — chronological event stream with color-coded kinds.
 */
const MAX_ROWS = 300;

function container() { return document.getElementById("timeline-list"); }

const KIND_COLORS = {
  tool_called: "hsl(var(--primary))",
  tool_result: "hsl(var(--success))",
  tool_error: "hsl(var(--destructive))",
  chat_user: "hsl(var(--foreground))",
  chat_assistant: "hsl(var(--foreground))",
  scan_started: "hsl(var(--primary))",
  scan_narrowed: "hsl(var(--primary))",
  watch_frozen: "hsl(195 80% 60%)",
  broker_status: "hsl(var(--muted-foreground))",
  dashboard_chat_request: "hsl(300 60% 60%)",
};

function timeShort(iso) {
  const m = iso?.match?.(/T(\d\d:\d\d:\d\d)/);
  return m ? m[1] : "";
}

export function appendEventRow(evt) {
  const root = container(); if (!root) return;
  const div = document.createElement("div");
  div.style.cssText = "padding:4px 10px;border-bottom:1px solid hsl(var(--border));font-size:10.5px;font-family:var(--font-mono);white-space:pre-wrap;word-break:break-all;line-height:1.5;";

  const ts = timeShort(evt.ts);
  const kind = evt.kind || "event";
  const color = KIND_COLORS[kind] || "hsl(var(--foreground))";
  const data = evt.data || {};

  const label = kind === "tool_called" ? `▶ ${data.name || "?"}`
    : kind === "tool_result" ? `✓ ${data.name || "?"}`
    : kind === "tool_error" ? `✗ ${data.name || "?"}`
    : kind === "chat_user" ? "👤 User"
    : kind === "chat_assistant" ? "🤖 AI"
    : kind;
  const detail = JSON.stringify(data, null, 0).slice(0, 260);

  div.innerHTML = `<span style="color:hsl(var(--muted-foreground));margin-right:8px;">${ts}</span><span style="color:${color}">${label}</span> <span style="color:hsl(var(--muted-foreground))">${detail}</span>`;

  root.prepend(div);
  while (root.children.length > MAX_ROWS) root.lastElementChild?.remove();
}

export function clearTimeline() {
  const root = container(); if (root) root.innerHTML = "";
}

export function bindTimeline({onEvent}) {
  onEvent((evt) => { if (evt) appendEventRow(evt); });
}
