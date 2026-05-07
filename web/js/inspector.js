/**
 * @file Inspector (right dock) — shows properties of the selected address.
 *
 * Displays: label (editable), address, type, current value (live),
 * new value input + write button, freeze toggle, remove button.
 * Selection comes from workspace clicks or watch_update events.
 */

let _selectedWatchId = null;
let _state = new Map(); // watch_id → row data (shared reference from workspace)

async function callMcp(name, args) {
  const res = await fetch("/mcp", {
    method: "POST",
    headers: {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    body: JSON.stringify({jsonrpc: "2.0", id: Date.now(), method: "tools/call", params: {name, arguments: args}}),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function pickWriteTool(vt) {
  const t = (vt || "int32").toLowerCase();
  if (t === "float" || t === "single") return "write_float";
  if (t === "double") return "write_double";
  if (t === "string") return "write_string";
  return "write_integer";
}

export function selectWatch(watchId) {
  _selectedWatchId = watchId;
  render();
}

export function setState(s) { _state = s; }

function selected() { return _selectedWatchId ? _state.get(_selectedWatchId) : null; }

function render() {
  const w = selected();
  const empty = document.getElementById("insp-empty");
  const detail = document.getElementById("insp-detail");
  if (!w) {
    if (empty) empty.hidden = false;
    if (detail) detail.hidden = true;
    return;
  }
  if (empty) empty.hidden = true;
  if (detail) detail.hidden = false;

  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? "—"; };
  const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ""; };

  setVal("insp-label", w.label || "");
  set("insp-addr", w.address);
  set("insp-vt", w.vt || "int32");
  setVal("insp-value", w.value !== undefined ? String(w.value) : "—");
  setVal("insp-freeze-value", w.freeze_value ?? (w.value !== undefined ? String(w.value) : ""));

  // Freeze toggle
  const fzToggle = document.getElementById("insp-freeze-toggle");
  const fzField = document.getElementById("insp-freeze-val-field");
  if (fzToggle) fzToggle.classList.toggle("on", !!w.frozen);
  if (fzField) fzField.hidden = !w.frozen;
}

// ── Event handlers ──

function bindInspectorEvents() {
  // Label edit
  document.getElementById("insp-label")?.addEventListener("change", async function() {
    const w = selected(); if (!w) return;
    w.label = this.value;
    try { await callMcp("cegm.watch_add", {address: w.address, vt: w.vt, label: w.label}); } catch (_) {}
    render();
  });

  // Write button
  document.getElementById("insp-write")?.addEventListener("click", async () => {
    const w = selected(); if (!w) return;
    const raw = document.getElementById("insp-new-value")?.value?.trim();
    if (!raw) return;
    try {
      await callMcp(pickWriteTool(w.vt), {address: w.address, value: raw});
    } catch (err) { console.error("write failed", err); }
  });

  // Freeze toggle
  document.getElementById("insp-freeze-toggle")?.addEventListener("click", async () => {
    const w = selected(); if (!w) return;
    try {
      if (w.frozen) {
        await callMcp("cegm.watch_unfreeze", {key: w.watch_id});
      } else {
        const fv = document.getElementById("insp-freeze-value")?.value?.trim() || String(w.value ?? "0");
        await callMcp("cegm.watch_freeze", {key: w.watch_id, value: fv});
      }
    } catch (err) { console.error("freeze toggle failed", err); }
  });

  // Remove
  document.getElementById("insp-remove")?.addEventListener("click", async () => {
    const w = selected(); if (!w) return;
    try { await callMcp("cegm.watch_remove", {key: w.watch_id}); } catch (err) { console.error("remove failed", err); }
  });
}

// ── Public bind ──

export function bindInspector({onEvent}) {
  bindInspectorEvents();

  onEvent((evt) => {
    if (!evt || !evt.kind) return;
    const data = evt.data || {};
    if (evt.kind === "watch_update") {
      const w = _state.get(data.watch_id);
      if (w && data.value !== undefined) w.value = data.value;
      if (w && data.ts) w.ts = data.ts;
      if (data.watch_id === _selectedWatchId) render();
    } else if (evt.kind === "watch_frozen" || evt.kind === "watch_unfrozen") {
      const w = _state.get(data.watch_id);
      if (w) w.frozen = evt.kind === "watch_frozen";
      if (data.watch_id === _selectedWatchId) render();
    } else if (evt.kind === "watch_removed") {
      if (data.key === _selectedWatchId) { _selectedWatchId = null; render(); }
    }
  });
}
