/**
 * @file "Tools" tab. Lists every MCP tool the broker proxies plus our
 * own ``cegm.*`` and any user-defined ``custom.*`` tools. Filterable
 * by name + description, grouped by inferred category. Refresh button
 * re-fetches via ``tools/list``.
 */
import {t} from "/js/i18n.js";

const PANEL_ID = "tools-panel";
const _state = {tools: []};

function panel() {
  return document.getElementById(PANEL_ID);
}

function categorize(name) {
  const n = name.toLowerCase();
  if (n.startsWith("cegm.")) return "cegm";
  if (n.startsWith("custom.")) return "custom";
  if (n.includes("aob") || n.includes("pattern")) return "aob";
  if (n.includes("scan")) return "scan";
  if (n.includes("pointer")) return "pointer";
  if (n.includes("break") || n.includes("watch") || n.includes("trace")) return "breakpoint";
  if (n.includes("disasm") || n.includes("asm") || n.includes("instruct")) return "disasm";
  if (n.includes("lua") || n === "evaluate_lua") return "lua";
  if (n.includes("inject") || n.includes("patch") || n.includes("hook") || n.includes("nop")) return "inject";
  if (n.includes("cheat") || n.includes("table")) return "cheat_table";
  if (n.includes("memory") || n.includes("read") || n.includes("write") || n.includes("bytes")) return "memory";
  return "other";
}

const CATEGORY_ORDER = [
  "cegm",
  "custom",
  "scan",
  "memory",
  "aob",
  "pointer",
  "disasm",
  "breakpoint",
  "inject",
  "lua",
  "cheat_table",
  "other",
];

async function fetchTools() {
  const res = await fetch("/mcp", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json, text/event-stream",
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: Math.floor(Math.random() * 1e9),
      method: "tools/list",
      params: {},
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const j = await res.json();
  return j?.result?.tools ?? [];
}

function ensureLayout() {
  const root = panel();
  if (!root) return null;
  if (root.dataset.built === "1") return root;
  root.replaceChildren();
  root.dataset.built = "1";

  const head = document.createElement("div");
  head.className = "flex items-center gap-2 border-b border-zinc-800 px-3 py-2";
  const input = document.createElement("input");
  input.type = "search";
  input.id = "tools-filter";
  input.dataset.i18nPlaceholder = "tools.search_placeholder";
  input.placeholder = t("tools.search_placeholder");
  input.className =
    "flex-1 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs font-mono";
  input.addEventListener("input", render);
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.dataset.i18n = "tools.refresh";
  refresh.textContent = t("tools.refresh");
  refresh.className = "rounded border border-zinc-700 px-2 py-1 text-xs hover:bg-zinc-800";
  refresh.addEventListener("click", () => loadAndRender());
  head.append(input, refresh);

  const list = document.createElement("div");
  list.id = "tools-list";
  list.className = "overflow-y-auto p-3 text-xs space-y-3";

  root.append(head, list);
  return root;
}

function render() {
  const root = ensureLayout();
  if (!root) return;
  const list = root.querySelector("#tools-list");
  const search = /** @type {HTMLInputElement | null} */ (
    root.querySelector("#tools-filter")
  );
  const q = (search?.value || "").trim().toLowerCase();
  list.replaceChildren();

  if (_state.tools.length === 0) {
    const empty = document.createElement("div");
    empty.className = "text-zinc-500";
    empty.dataset.i18n = "tools.empty";
    empty.textContent = t("tools.empty");
    list.append(empty);
    return;
  }

  const groups = new Map();
  for (const tool of _state.tools) {
    if (q) {
      const blob = (tool.name + " " + (tool.description || "")).toLowerCase();
      if (!blob.includes(q)) continue;
    }
    const cat = categorize(tool.name);
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat).push(tool);
  }

  for (const cat of CATEGORY_ORDER) {
    const tools = groups.get(cat);
    if (!tools || tools.length === 0) continue;
    const section = document.createElement("section");
    const h = document.createElement("h3");
    h.className = "font-mono text-[10px] uppercase tracking-wider text-zinc-500 mb-1";
    h.dataset.i18n = `tools.cat_${cat}`;
    h.textContent = t(`tools.cat_${cat}`) + `  (${tools.length})`;
    section.append(h);
    const ul = document.createElement("ul");
    ul.className = "space-y-1";
    for (const tool of tools.sort((a, b) => a.name.localeCompare(b.name))) {
      const li = document.createElement("li");
      li.className = "rounded border border-zinc-800 bg-zinc-900/40 px-2 py-1";
      const top = document.createElement("div");
      top.className = "font-mono text-zinc-200";
      top.textContent = tool.name;
      li.append(top);
      if (tool.description) {
        const desc = document.createElement("div");
        desc.className = "text-zinc-500 mt-0.5";
        desc.textContent = tool.description;
        li.append(desc);
      }
      ul.append(li);
    }
    section.append(ul);
    list.append(section);
  }

  if (list.childElementCount === 0) {
    const empty = document.createElement("div");
    empty.className = "text-zinc-500";
    empty.textContent = "(no matches)";
    list.append(empty);
  }
}

async function loadAndRender() {
  try {
    _state.tools = await fetchTools();
  } catch (err) {
    console.warn("tools.fetch_failed", err);
    _state.tools = [];
  }
  render();
}

export function bindTools({onEvent}) {
  ensureLayout();
  loadAndRender();
  // Refresh whenever a custom tool is defined / undefined upstream.
  onEvent((evt) => {
    if (evt?.kind === "dynamic_tool_defined" || evt?.kind === "dynamic_tool_undefined") {
      loadAndRender();
    }
  });
}
