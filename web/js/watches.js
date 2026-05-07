/**
 * @file "Watches" tab. Listens for ``watch_added`` / ``watch_update`` /
 * ``watch_removed`` WebSocket events and renders a live-updating grid
 * of (address, value, label, last seen). Remove button issues the
 * ``cegm.watch_remove`` MCP call directly.
 */
import {t} from "/js/i18n.js";

const PANEL_ID = "watch-panel";
const state = new Map(); // watch_id → row data

function panel() {
  return document.getElementById(PANEL_ID);
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

function timeShort(iso) {
  const m = iso?.match?.(/T(\d\d:\d\d:\d\d)/);
  return m ? m[1] : "";
}

function ensureTable() {
  const root = panel();
  if (!root) return null;
  let table = root.querySelector("table");
  if (!table) {
    table = document.createElement("table");
    table.className = "w-full text-xs font-mono";
    const thead = document.createElement("thead");
    thead.className = "text-[10px] uppercase tracking-wider text-zinc-500";
    const trh = document.createElement("tr");
    for (const key of ["watches.address", "watches.value", "watches.label", "watches.last_seen", "watches.actions"]) {
      const th = document.createElement("th");
      th.className = "px-2 py-1 text-left";
      if (key) {
        th.dataset.i18n = key;
        th.textContent = t(key);
      }
      trh.append(th);
    }
    thead.append(trh);
    const tbody = document.createElement("tbody");
    table.append(thead, tbody);
    root.replaceChildren(table);
  }
  return table.querySelector("tbody");
}

function render() {
  const tbody = ensureTable();
  if (!tbody) return;
  tbody.replaceChildren();
  if (state.size === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.className = "px-2 py-3 text-zinc-500";
    td.dataset.i18n = "watches.empty";
    td.textContent = t("watches.empty");
    tr.append(td);
    tbody.append(tr);
    return;
  }
  for (const w of state.values()) {
    const tr = document.createElement("tr");
    tr.className = "border-t border-zinc-800";

    function cell(content, classes = "") {
      const td = document.createElement("td");
      td.className = "px-2 py-1 align-top " + classes;
      if (content instanceof Node) td.append(content);
      else td.textContent = String(content ?? "");
      return td;
    }

    tr.append(cell(w.address, "text-zinc-300"));
    if (w.error) {
      tr.append(cell(w.error, "text-red-400"));
    } else {
      const v = typeof w.value === "object" ? JSON.stringify(w.value) : String(w.value ?? "—");
      const vc = w.frozen ? "text-cyan-300 font-semibold" : "text-emerald-300";
      tr.append(cell(v, vc));
    }
    tr.append(cell(w.label || "", "text-zinc-500"));
    tr.append(cell(timeShort(w.ts), "text-zinc-500"));

    // Actions cell
    const actionsTd = document.createElement("td");
    actionsTd.className = "px-2 py-1 flex flex-wrap gap-1";

    // Freeze button
    if (!w.frozen) {
      const fzBtn = document.createElement("button");
      fzBtn.type = "button";
      fzBtn.textContent = "❄";
      fzBtn.title = "Freeze at current value";
      fzBtn.className = "rounded border border-zinc-700 px-1.5 py-0.5 text-[11px] hover:bg-cyan-900/40";
      fzBtn.addEventListener("click", async () => {
        const target = window.prompt("Freeze value:", String(w.value ?? ""));
        if (target == null) return;
        try {
          await callMcp("cegm.watch_freeze", {key: w.watch_id, value: target});
        } catch (err) {
          console.error(err);
        }
      });
      actionsTd.append(fzBtn);
    } else {
      const ufBtn = document.createElement("button");
      ufBtn.type = "button";
      ufBtn.textContent = "🧊";
      ufBtn.title = `Frozen at ${w.freeze_value}. Click to unfreeze.`;
      ufBtn.className = "rounded border border-cyan-700 bg-cyan-900/30 px-1.5 py-0.5 text-[11px] hover:bg-cyan-900/60";
      ufBtn.addEventListener("click", async () => {
        try {
          await callMcp("cegm.watch_unfreeze", {key: w.watch_id});
        } catch (err) {
          console.error(err);
        }
      });
      actionsTd.append(ufBtn);
    }

    const rmBtn = document.createElement("button");
    rmBtn.type = "button";
    rmBtn.textContent = "✕";
    rmBtn.title = t("watches.remove");
    rmBtn.className = "rounded border border-zinc-700 px-1.5 py-0.5 text-[11px] hover:bg-red-900/40 text-red-400";
    rmBtn.addEventListener("click", async () => {
      try {
        await callMcp("cegm.watch_remove", {key: w.watch_id});
      } catch (err) {
        console.error(err);
      }
    });
    actionsTd.append(rmBtn);

    tr.append(actionsTd);

    tbody.append(tr);
  }
}

function handleEvent(evt) {
  if (!evt || !evt.kind) return;
  const data = evt.data || {};
  if (evt.kind === "watch_added") {
    state.set(data.watch_id, {
      watch_id: data.watch_id,
      address: data.address,
      vt: data.vt,
      label: data.label || "",
      value: undefined,
      ts: "",
    });
    render();
  } else if (evt.kind === "watch_update") {
    const row = state.get(data.watch_id) || {
      watch_id: data.watch_id,
      address: data.address,
      vt: data.vt,
      label: data.label || "",
    };
    row.value = data.value;
    row.ts = data.ts || row.ts;
    row.error = data.error || null;
    state.set(row.watch_id, row);
    render();
  } else if (evt.kind === "watch_frozen") {
    const row = state.get(data.watch_id);
    if (row) {
      row.frozen = true;
      row.freeze_value = data.freeze_value;
      state.set(row.watch_id, row);
      render();
    }
  } else if (evt.kind === "watch_unfrozen") {
    const row = state.get(data.watch_id);
    if (row) {
      row.frozen = false;
      row.freeze_value = null;
      state.set(row.watch_id, row);
      render();
    }
  } else if (evt.kind === "watch_removed") {
    // The event uses the address/key the user passed in; we may need to
    // match by either watch_id or address.
    const key = data.key;
    for (const [wid, w] of state) {
      if (wid === key || w.address === key) {
        state.delete(wid);
      }
    }
    render();
  }
}

export function bindWatches({onEvent}) {
  render();
  onEvent(handleEvent);
}
