/**
 * @file Tools browser — lists proxied + CEGM + custom tools, filterable.
 * Server-side category tags ([memory_read], [scan], etc.) are displayed.
 */
const _state = {tools: []};

async function fetchTools() {
  const res = await fetch("/mcp", {
    method: "POST",
    headers: {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    body: JSON.stringify({jsonrpc: "2.0", id: Date.now(), method: "tools/list", params: {}}),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const j = await res.json();
  return j?.result?.tools ?? [];
}

function groupByCategory(tools) {
  const groups = new Map();
  for (const t of tools) {
    // Extract [category] prefix from server-enriched descriptions
    const m = (t.description || "").match(/^\[(\w+)\]\s*/);
    const cat = m ? m[1] : "other";
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat).push(t);
  }
  // Sort categories
  const order = ["process", "memory_read", "memory_write", "scan", "aob", "pointer",
                 "disasm", "breakpoint", "inject", "freeze", "cheat_table", "symbol",
                 "cegm", "custom", "utility", "other"];
  const sorted = new Map();
  for (const cat of order) { if (groups.has(cat)) sorted.set(cat, groups.get(cat)); }
  for (const [cat, items] of groups) { if (!sorted.has(cat)) sorted.set(cat, items); }
  return sorted;
}

function render() {
  const list = document.getElementById("tools-list");
  const filter = document.getElementById("tools-filter");
  if (!list) return;
  const q = (filter?.value || "").trim().toLowerCase();

  list.innerHTML = "";
  if (_state.tools.length === 0) {
    list.innerHTML = '<div style="text-align:center;padding:20px;color:hsl(var(--muted-foreground));font-size:12px;">Loading tools…</div>';
    return;
  }

  const groups = groupByCategory(_state.tools);
  let shown = 0;

  for (const [cat, tools] of groups) {
    const filtered = q ? tools.filter(t => (t.name + " " + (t.description || "")).toLowerCase().includes(q)) : tools;
    if (!filtered.length) continue;
    shown += filtered.length;

    const section = document.createElement("div");
    section.style.marginBottom = "12px";

    const hdr = document.createElement("div");
    hdr.style.cssText = "font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:hsl(var(--muted-foreground));padding:4px 0 2px;";
    hdr.textContent = `${cat} (${filtered.length})`;
    section.append(hdr);

    for (const tool of filtered.sort((a, b) => a.name.localeCompare(b.name))) {
      const row = document.createElement("div");
      row.style.cssText = "padding:3px 8px;border-bottom:1px solid hsl(var(--border));";
      row.innerHTML = `<span style="font-family:var(--font-mono);font-size:11px;color:hsl(var(--foreground))">${tool.name}</span>
        <span style="font-size:10px;color:hsl(var(--muted-foreground));margin-left:8px;">${(tool.description || "").replace(/^\[\w+\]\s*/, "")}</span>`;
      section.append(row);
    }
    list.append(section);
  }

  if (!shown && q) {
    list.innerHTML = '<div style="text-align:center;padding:20px;color:hsl(var(--muted-foreground));font-size:12px;">No tools match.</div>';
  }
}

async function loadAndRender() {
  try { _state.tools = await fetchTools(); } catch (_) { _state.tools = []; }
  render();
}

export function bindTools({onEvent}) {
  document.getElementById("tools-filter")?.addEventListener("input", render);
  document.getElementById("tools-refresh")?.addEventListener("click", loadAndRender);
  loadAndRender();
  onEvent((evt) => {
    if (evt?.kind === "dynamic_tool_defined" || evt?.kind === "dynamic_tool_undefined") loadAndRender();
  });
}
