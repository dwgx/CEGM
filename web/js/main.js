/**
 * @file Dashboard entry point — Unity-editor layout.
 *
 * Wires: sidebar nav, content tabs, workspace, chat, scans, timeline,
 * tools, inspector, console, status bar, settings drawer, WebSocket.
 */
import {fetchHealth} from "/js/api.js";
import {openEventStream} from "/js/ws.js";
import {appendConsoleLine, clearConsole} from "/js/console.js";
import {bindChat} from "/js/chat.js";
import {bindWorkspace} from "/js/workspace.js";
import {bindScans} from "/js/scans.js";
import {bindTimeline} from "/js/timeline.js";
import {bindTools} from "/js/tools.js";
import {bindSettings} from "/js/settings.js";
import {bindInspector} from "/js/inspector.js";
import {bindLua} from "/js/lua.js";
import {bindHex} from "/js/hex.js";
import {flashTabTitle, desktopNotify} from "/js/notify.js";
import {submitMessage} from "/js/chat.js";
import {applyTranslations, getLang, setLang, t} from "/js/i18n.js";

// ── Status indicators ──────────────────────────────────────────────────

function setStatus(label) {
  const dot = document.getElementById("tb-dot");
  const txt = document.getElementById("tb-status-text");
  if (dot) { dot.className = "toolbar-dot"; dot.classList.add(label === "connected" ? "on" : label === "connecting" ? "connecting" : "off"); }
  if (txt) txt.textContent = label;
}

// ── Sidebar nav ↔ content tabs sync ───────────────────────────────────

function activateNav(key) {
  for (const el of document.querySelectorAll("#sidebar .sidebar-item")) {
    el.classList.toggle("active", el.dataset.nav === key);
  }
  for (const el of document.querySelectorAll("#content-tabs .content-tab")) {
    el.classList.toggle("active", el.dataset.content === key);
  }
  for (const el of document.querySelectorAll(".content-panel")) {
    el.classList.toggle("active", el.id === `panel-${key}`);
  }
  localStorage.setItem("cegm-active-nav", key);
}

function bindNavigation() {
  for (const el of document.querySelectorAll("#sidebar .sidebar-item")) {
    el.addEventListener("click", () => activateNav(el.dataset.nav));
  }
  for (const el of document.querySelectorAll("#content-tabs .content-tab")) {
    el.addEventListener("click", () => activateNav(el.dataset.content));
  }
  const saved = localStorage.getItem("cegm-active-nav") || "workspace";
  activateNav(saved);
}

// ── Event broker (multiplex WebSocket events to panels) ────────────────

function makeBroker() {
  const handlers = new Set();
  return {
    on(fn) { handlers.add(fn); return () => handlers.delete(fn); },
    emit(evt) { for (const h of handlers) { try { h(evt); } catch (err) { console.warn("event handler threw", err); } } },
  };
}

// ── Init ───────────────────────────────────────────────────────────────

function init() {
  document.documentElement.lang = getLang();
  applyTranslations();
  setStatus("connecting");

  bindNavigation();

  // Chat
  bindChat({formId: "chat-form", inputId: "chat-input", logId: "chat-log"});

  // Settings
  bindSettings({
    toggleId: "btn-settings",
    drawerId: "settings-drawer",
    formId: "settings-form",
    closeId: "settings-close",
  });

  // Language toggle — live switch, no reload
  document.getElementById("btn-lang")?.addEventListener("click", () => {
    const cur = getLang();
    const next = cur === "zh" ? "en" : "zh";
    setLang(next);
    document.getElementById("btn-lang").textContent = next === "zh" ? "EN" : "中";
  });
  // Set initial lang toggle text
  const langBtn = document.getElementById("btn-lang");
  if (langBtn) langBtn.textContent = getLang() === "zh" ? "EN" : "中";

  // Console clear
  document.getElementById("console-clear")?.addEventListener("click", clearConsole);
  // Console resize handle
  const consoleHeader = document.getElementById("console-header");
  const consoleArea = document.getElementById("console-area");
  if (consoleHeader && consoleArea) {
    let dragging = false;
    let startY = 0, startH = 0;
    consoleHeader.addEventListener("mousedown", (e) => {
      dragging = true; startY = e.clientY; startH = consoleArea.offsetHeight;
      document.body.style.cursor = "row-resize"; document.body.style.userSelect = "none";
    });
    document.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const delta = startY - e.clientY;
      const h = Math.max(80, Math.min(400, startH + delta));
      consoleArea.style.minHeight = h + "px";
      consoleArea.style.maxHeight = h + "px";
    });
    document.addEventListener("mouseup", () => {
      dragging = false; document.body.style.cursor = ""; document.body.style.userSelect = "";
    });
  }

  // Event bus
  const evtBroker = makeBroker();
  bindWorkspace({onEvent: evtBroker.on});
  bindScans({onEvent: evtBroker.on});
  bindTimeline({onEvent: evtBroker.on});
  bindTools({onEvent: evtBroker.on});
  bindInspector({onEvent: evtBroker.on});
  bindLua();
  bindHex();

  // Probe
  probeBroker();

  // WebSocket
  openEventStream({
    onOpen: () => setStatus("connected"),
    onClose: () => setStatus("disconnected"),
    onEvent: (evt) => {
      if (evt?.kind === "dashboard_chat_request") {
        const msg = evt?.data?.message;
        if (typeof msg === "string" && msg) {
          activateNav("chat"); submitMessage(msg); flashTabTitle(); desktopNotify(msg);
        }
        return;
      }
      if (evt?.kind === "broker_reload") {
        console.log("CEGM: hot reload triggered, refreshing…");
        window.location.reload();
        return;
      }
      appendConsoleLine(evt);
      evtBroker.emit(evt);
    },
  });
}

async function probeBroker() {
  try {
    const h = await fetchHealth();
    setStatus("connected");
    document.getElementById("tb-process").textContent =
      h?.proxy?.available ? "attached" : "no process";
    const sb = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
    sb("sb-version", `v${h?.version || "?"}`);
    sb("sb-proxy", `proxy: ${h?.proxy?.available ? "live" : "down"}`);
    sb("sb-tools", `tools: ${h?.proxy?.tool_count || 0}`);
  } catch (_) {
    setStatus("disconnected");
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, {once: true});
} else {
  init();
}
