/**
 * @file Scans panel — card list of scan records.
 */
const state = new Map();

async function callMcp(name, args) {
  const res = await fetch("/mcp", {
    method: "POST",
    headers: {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    body: JSON.stringify({jsonrpc: "2.0", id: Date.now(), method: "tools/call", params: {name, arguments: args}}),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function render() {
  const root = document.getElementById("scan-list");
  if (!root) return;
  root.innerHTML = "";
  const records = [...state.values()].reverse();
  if (!records.length) {
    root.innerHTML = '<div style="text-align:center;padding:20px;color:hsl(var(--muted-foreground));font-size:12px;">No scans yet. Use the chat to find values.</div>';
    return;
  }
  for (const rec of records) {
    const card = document.createElement("div");
    card.className = "card";
    card.style.marginBottom = "8px";

    const hdr = document.createElement("div");
    hdr.className = "card-header";
    hdr.style.display = "flex"; hdr.style.justifyContent = "space-between"; hdr.style.alignItems = "center";
    hdr.innerHTML = `<span style="font-family:var(--font-mono);font-size:11px;">${rec.value} <span style="color:hsl(var(--muted-foreground))">(${rec.vt})</span></span>
      <span class="badge badge-primary">${rec.count} hits</span>`;
    card.append(hdr);

    const body = document.createElement("div");
    body.className = "card-body";
    body.style.fontSize = "11px";

    // Preview addresses
    const previews = (rec.results || []).slice(0, 5);
    if (previews.length) {
      const ol = document.createElement("ol");
      ol.style.cssText = "list-style:none;margin:0 0 6px;padding:0;";
      for (const r of previews) {
        const li = document.createElement("li");
        li.style.cssText = "font-family:var(--font-mono);font-size:10px;display:flex;justify-content:space-between;padding:1px 0;";
        li.innerHTML = `<span>${r.address}</span><span style="color:hsl(var(--muted-foreground))">${r.value ?? ""}</span>`;
        ol.append(li);
      }
      if ((rec.results || []).length > 5) {
        const more = document.createElement("li");
        more.textContent = `… and ${rec.results.length - 5} more`;
        more.style.cssText = "color:hsl(var(--muted-foreground));font-size:10px;";
        ol.append(more);
      }
      body.append(ol);
    }

    // Scan ID
    const idLine = document.createElement("div");
    idLine.style.cssText = "font-size:9.5px;color:hsl(var(--muted-foreground));font-family:var(--font-mono);margin-bottom:6px;";
    idLine.textContent = rec.scan_id + (rec.parent_id ? ` (narrowed from ${rec.parent_id})` : "");
    body.append(idLine);

    // Actions
    const actions = document.createElement("div");
    actions.style.display = "flex"; actions.style.gap = "4px";
    const narrowBtn = document.createElement("button");
    narrowBtn.className = "btn btn-outline btn-xs";
    narrowBtn.textContent = "Narrow";
    narrowBtn.addEventListener("click", async () => {
      const v = window.prompt(`New value for ${rec.value}:`, rec.value);
      if (v == null) return;
      try { await callMcp("cegm.scan_narrow", {op: "exact", value: String(v)}); } catch (err) { console.error(err); }
    });
    const dropBtn = document.createElement("button");
    dropBtn.className = "btn btn-ghost btn-xs";
    dropBtn.textContent = "Drop";
    dropBtn.addEventListener("click", async () => {
      try { await callMcp("cegm.scan_drop", {scan_id: rec.scan_id}); state.delete(rec.scan_id); render(); } catch (err) { console.error(err); }
    });
    actions.append(narrowBtn, dropBtn);
    body.append(actions);

    card.append(body);
    root.append(card);
  }
}

function handleEvent(evt) {
  if (!evt || !evt.kind) return;
  const data = evt.data || {};
  if (evt.kind === "scan_started" || evt.kind === "scan_narrowed") {
    state.set(data.scan_id, {
      scan_id: data.scan_id, parent_id: data.parent_id || null,
      value: data.value ?? `(${data.op || "?"})`, vt: data.vt || "?", count: data.count ?? 0,
      results: data.results || [],
    });
    render();
  } else if (evt.kind === "scan_dropped") {
    state.delete(data.scan_id); render();
  }
}

export function bindScans({onEvent}) { render(); onEvent(handleEvent); }
