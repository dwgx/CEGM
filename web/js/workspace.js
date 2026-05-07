/**
 * @file Workspace — the main memory editor table.
 *
 * Shows all watched addresses in a data-table. Supports:
 *   Inline editing (click to edit value/name → Enter to save)
 *   Freeze/unfreeze via toggle button
 *   Selection → updates the Inspector panel
 *   Add-new-address toolbar
 */

import {selectWatch, setState} from "/js/inspector.js";

const state = new Map();
let editingWatchId = null;
let editingField = null;

function callMcp(name, args) {
  return fetch("/mcp", {
    method: "POST",
    headers: {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    body: JSON.stringify({jsonrpc: "2.0", id: Date.now(), method: "tools/call", params: {name, arguments: args}}),
  }).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); });
}

function pickWriteTool(vt) {
  const t = (vt || "int32").toLowerCase();
  if (t === "float" || t === "single") return "write_float";
  if (t === "double") return "write_double";
  if (t === "string") return "write_string";
  return "write_integer";
}

function fmt(v) {
  if (v === undefined || v === null) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function timeShort(iso) {
  const m = iso?.match?.(/T(\d\d:\d\d:\d\d)/);
  return m ? m[1] : "";
}

// ── render ─────────────────────────────────────────────────────────────

function render() {
  const tbody = document.getElementById("ws-tbody");
  const empty = document.getElementById("ws-empty");
  const summary = document.getElementById("ws-summary");
  if (!tbody) return;

  const rows = [...state.values()];
  if (summary) {
    const frozen = rows.filter(r => r.frozen).length;
    summary.textContent = `${rows.length} addr${rows.length !== 1 ? "s" : ""}` + (frozen ? ` · ${frozen} frozen` : "");
  }

  if (rows.length === 0) {
    tbody.innerHTML = "";
    if (empty) empty.style.display = "flex";
    return;
  }
  if (empty) empty.style.display = "none";

  tbody.innerHTML = "";

  for (const w of rows) {
    const tr = document.createElement("tr");
    if (w.frozen) tr.classList.add("frozen");
    tr.addEventListener("click", () => selectWatch(w.watch_id));

    // Name
    const nameTd = document.createElement("td");
    if (editingWatchId === w.watch_id && editingField === "label") {
      const inp = document.createElement("input");
      inp.type = "text"; inp.value = w.label || "";
      inp.className = "input input-mono input-sm"; inp.style.width = "100%";
      inp.addEventListener("keydown", async (e) => {
        if (e.key === "Enter") { e.preventDefault(); w.label = inp.value.trim() || w.address; doneEditing(); try { await callMcp("cegm.watch_add", {address: w.address, vt: w.vt, label: w.label}); } catch (_) {} }
        if (e.key === "Escape") doneEditing();
      });
      inp.addEventListener("blur", () => setTimeout(doneEditing, 100));
      nameTd.append(inp);
      setTimeout(() => inp.focus(), 0);
    } else {
      nameTd.textContent = w.label || w.address;
      nameTd.style.cursor = "pointer";
      nameTd.title = "Click to rename";
      nameTd.addEventListener("dblclick", (e) => { e.stopPropagation(); editingWatchId = w.watch_id; editingField = "label"; render(); });
    }
    tr.append(nameTd);

    // Address
    const addrTd = document.createElement("td");
    addrTd.textContent = w.address;
    addrTd.style.color = "hsl(var(--muted-foreground))";
    tr.append(addrTd);

    // Type
    const vtTd = document.createElement("td");
    vtTd.textContent = w.vt || "int32";
    vtTd.style.color = "hsl(var(--muted-foreground))";
    tr.append(vtTd);

    // Value
    const valTd = document.createElement("td");
    valTd.style.fontWeight = "600";
    if (w.error) {
      valTd.textContent = w.error;
      valTd.style.color = "hsl(var(--destructive))";
    } else if (editingWatchId === w.watch_id && editingField === "value") {
      const inp = document.createElement("input");
      inp.type = "text"; inp.value = fmt(w.value);
      inp.className = "input input-mono input-sm"; inp.style.width = "90px";
      inp.addEventListener("keydown", async (e) => {
        if (e.key === "Enter") { e.preventDefault(); const raw = inp.value.trim(); doneEditing(); if (raw) { try { await callMcp(pickWriteTool(w.vt), {address: w.address, value: raw}); } catch (_) {} } }
        if (e.key === "Escape") doneEditing();
      });
      inp.addEventListener("blur", () => setTimeout(doneEditing, 100));
      valTd.append(inp);
      setTimeout(() => inp.select(), 0);
    } else {
      valTd.textContent = fmt(w.value);
      valTd.style.color = w.frozen ? "hsl(var(--primary))" : "hsl(var(--success))";
      valTd.style.cursor = "pointer";
      valTd.title = "Double-click to edit";
      valTd.addEventListener("dblclick", (e) => { e.stopPropagation(); editingWatchId = w.watch_id; editingField = "value"; render(); });
    }
    tr.append(valTd);

    // Seen
    const seenTd = document.createElement("td");
    seenTd.textContent = timeShort(w.ts) || "—";
    seenTd.style.cssText = "color:hsl(var(--muted-foreground));font-size:10px;";
    tr.append(seenTd);

    // Freeze toggle
    const fzTd = document.createElement("td");
    const fzBtn = document.createElement("button");
    fzBtn.type = "button";
    fzBtn.className = "toggle" + (w.frozen ? " on" : "");
    fzBtn.innerHTML = '<span class="toggle-knob"></span>';
    fzBtn.title = w.frozen ? "Unfreeze" : "Freeze";
    fzBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        if (w.frozen) {
          await callMcp("cegm.watch_unfreeze", {key: w.watch_id});
        } else {
          const target = window.prompt("Freeze at:", fmt(w.value));
          if (target == null) return;
          await callMcp("cegm.watch_freeze", {key: w.watch_id, value: target});
        }
      } catch (err) { console.error(err); }
    });
    fzTd.append(fzBtn);
    tr.append(fzTd);

    // Remove
    const rmTd = document.createElement("td");
    const rmBtn = document.createElement("button");
    rmBtn.type = "button";
    rmBtn.textContent = "✕";
    rmBtn.className = "btn btn-ghost btn-xs";
    rmBtn.style.color = "hsl(var(--muted-foreground))";
    rmBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      try { await callMcp("cegm.watch_remove", {key: w.watch_id}); } catch (err) { console.error(err); }
    });
    rmTd.append(rmBtn);
    tr.append(rmTd);

    tbody.append(tr);
  }
}

function doneEditing() { editingWatchId = null; editingField = null; render(); }

// ── Add button ─────────────────────────────────────────────────────────

function bindAdd() {
  document.getElementById("ws-add")?.addEventListener("click", async () => {
    const addr = document.getElementById("ws-addr")?.value?.trim();
    if (!addr) return;
    const vt = document.getElementById("ws-vt")?.value || "int32";
    const label = document.getElementById("ws-label")?.value?.trim() || addr;
    try {
      await callMcp("cegm.watch_add", {address: addr, vt, label});
      const a = document.getElementById("ws-addr"); if (a) a.value = "";
      const l = document.getElementById("ws-label"); if (l) l.value = "";
    } catch (err) { console.error(err); }
  });
}

// ── event handling ─────────────────────────────────────────────────────

function handleEvent(evt) {
  if (!evt || !evt.kind) return;
  const data = evt.data || {};

  if (evt.kind === "watch_added") {
    state.set(data.watch_id, {
      watch_id: data.watch_id, address: data.address, vt: data.vt || "int32",
      label: data.label || "", value: undefined, ts: "", frozen: false, freeze_value: null, error: null,
    });
    render();
    // Update status bar
    const sb = document.getElementById("sb-watches"); if (sb) sb.textContent = `watches: ${state.size}`;
  } else if (evt.kind === "watch_update") {
    const existing = state.get(data.watch_id);
    const row = existing || { watch_id: data.watch_id, address: data.address, vt: data.vt || "int32", label: data.label || "", frozen: false, freeze_value: null, error: null };
    row.value = data.value; row.ts = data.ts || row.ts; row.error = data.error || null; row.frozen = data.frozen || row.frozen;
    state.set(row.watch_id, row);
    render();
  } else if (evt.kind === "watch_frozen") {
    const row = state.get(data.watch_id);
    if (row) { row.frozen = true; row.freeze_value = data.freeze_value; state.set(row.watch_id, row); render(); }
  } else if (evt.kind === "watch_unfrozen") {
    const row = state.get(data.watch_id);
    if (row) { row.frozen = false; row.freeze_value = null; state.set(row.watch_id, row); render(); }
  } else if (evt.kind === "watch_removed") {
    for (const [wid, w] of state) { if (wid === data.key || w.address === data.key) { state.delete(wid); } }
    render();
    const sb = document.getElementById("sb-watches"); if (sb) sb.textContent = `watches: ${state.size}`;
  }
}

export function bindWorkspace({onEvent}) {
  bindAdd();
  setState(state);
  render();
  onEvent(handleEvent);
}
