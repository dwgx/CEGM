/**
 * @file "Scans" tab. Listens for ``scan_started`` / ``scan_narrowed`` /
 * ``scan_dropped`` WebSocket events and renders one card per scan with
 * its hit count, value, narrow / drop actions, and a preview of the
 * top hit addresses (delivered inline by ``cegm.scan``).
 *
 * Narrow / Drop buttons short-circuit the chat: they call our broker's
 * own MCP tools through a tiny ``/api/chat`` shim that resolves to a
 * tool call. To keep this module simple we POST directly to ``/mcp``
 * with a JSON-RPC payload — same path external clients use, no extra
 * REST surface to maintain.
 */
import {t} from "/js/i18n.js";

const PANEL_ID = "scan-panel";
const MAX_RENDERED_PREVIEWS = 5;

const state = new Map(); // scan_id → record

function panel() {
  return document.getElementById(PANEL_ID);
}

function emptyMessage() {
  const li = document.createElement("li");
  li.className = "text-zinc-500 text-sm py-2";
  li.dataset.i18n = "scans.empty";
  li.textContent = t("scans.empty");
  return li;
}

function ensureList() {
  const root = panel();
  if (!root) return null;
  let ul = root.querySelector("ol");
  if (!ul) {
    ul = document.createElement("ol");
    ul.className = "space-y-2 p-3";
    root.replaceChildren(ul);
  }
  return ul;
}

async function callMcp(name, args) {
  const res = await fetch("/mcp", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json, text/event-stream",
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: Math.floor(Math.random() * 1e9),
      method: "tools/call",
      params: {name, arguments: args},
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function render() {
  const ul = ensureList();
  if (!ul) return;
  ul.replaceChildren();
  const records = [...state.values()].reverse();
  if (records.length === 0) {
    ul.append(emptyMessage());
    return;
  }
  for (const rec of records) {
    const li = document.createElement("li");
    li.className =
      "rounded border border-zinc-800 bg-zinc-900/40 p-3 text-xs space-y-2";

    const head = document.createElement("div");
    head.className = "flex items-center justify-between gap-2";

    const meta = document.createElement("div");
    meta.className = "font-mono leading-tight";
    const valueLine = document.createElement("div");
    valueLine.className = "text-zinc-300";
    valueLine.textContent = `${rec.value} (${rec.vt})`;
    const idLine = document.createElement("div");
    idLine.className = "text-[10px] text-zinc-500";
    idLine.textContent = rec.scan_id;
    if (rec.parent_id) {
      const p = document.createElement("div");
      p.className = "text-[10px] text-zinc-500";
      p.textContent = `${t("scans.narrowed_from")} ${rec.parent_id}`;
      idLine.append(document.createElement("br"), p);
    }
    meta.append(valueLine, idLine);

    const counts = document.createElement("div");
    counts.className = "text-right";
    const big = document.createElement("div");
    big.className = "text-lg font-semibold text-emerald-400";
    big.textContent = String(rec.count);
    const small = document.createElement("div");
    small.className = "text-[10px] uppercase tracking-wider text-zinc-500";
    small.dataset.i18n = "scans.count_label";
    small.textContent = t("scans.count_label");
    counts.append(big, small);

    head.append(meta, counts);

    const preview = document.createElement("ol");
    preview.className = "font-mono text-[11px] text-zinc-400 space-y-0.5";
    const previews = (rec.results || []).slice(0, MAX_RENDERED_PREVIEWS);
    for (const r of previews) {
      const row = document.createElement("li");
      row.textContent = `${r.address}  ${r.value ?? ""}`;
      preview.append(row);
    }

    const actions = document.createElement("div");
    actions.className = "flex gap-2 pt-1";
    const narrow = document.createElement("button");
    narrow.type = "button";
    narrow.dataset.i18n = "scans.narrow";
    narrow.textContent = t("scans.narrow");
    narrow.className =
      "rounded border border-zinc-700 px-2 py-0.5 text-[11px] hover:bg-zinc-800";
    narrow.addEventListener("click", async () => {
      const v = window.prompt(`${rec.value} → ?`, rec.value);
      if (v == null) return;
      try {
        await callMcp("cegm.scan_narrow", {op: "exact", value: String(v)});
      } catch (err) {
        console.error(err);
      }
    });
    const drop = document.createElement("button");
    drop.type = "button";
    drop.dataset.i18n = "scans.drop";
    drop.textContent = t("scans.drop");
    drop.className =
      "rounded border border-zinc-800 px-2 py-0.5 text-[11px] text-zinc-400 hover:bg-zinc-800";
    drop.addEventListener("click", async () => {
      try {
        await callMcp("cegm.scan_drop", {scan_id: rec.scan_id});
      } catch (err) {
        console.error(err);
      }
      state.delete(rec.scan_id);
      render();
    });
    actions.append(narrow, drop);

    li.append(head, preview, actions);
    ul.append(li);
  }
}

function handleEvent(evt) {
  if (!evt || !evt.kind) return;
  const data = evt.data || {};
  if (evt.kind === "scan_started" || evt.kind === "scan_narrowed") {
    state.set(data.scan_id, {
      scan_id: data.scan_id,
      parent_id: data.parent_id || null,
      value: data.value ?? `(${data.op || "?"})`,
      vt: data.vt || "?",
      count: data.count ?? 0,
      results: data.results || [],
    });
    render();
  } else if (evt.kind === "scan_dropped") {
    state.delete(data.scan_id);
    render();
  } else if (evt.kind === "tool_result" && data.name === "cegm.scan") {
    // ``cegm.scan`` already publishes ``scan_started`` itself; nothing extra here.
  }
}

export function bindScans({onEvent}) {
  render();
  onEvent(handleEvent);
}
