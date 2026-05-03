/**
 * @file Dashboard entry point. Wires DOM event handlers to the modular
 * subsystems (api / ws / timeline / chat / settings / i18n / notify /
 * tabs / scans / watches / tools) and kicks off the WebSocket connection.
 */
import {fetchHealth} from "/js/api.js";
import {openEventStream} from "/js/ws.js";
import {appendEventRow, clearTimeline} from "/js/timeline.js";
import {bindChat, submitMessage} from "/js/chat.js";
import {bindSettings} from "/js/settings.js";
import {applyTranslations, getLang, setLang, t} from "/js/i18n.js";
import {flashTabTitle, desktopNotify} from "/js/notify.js";
import {bindTabs} from "/js/tabs.js";
import {bindScans} from "/js/scans.js";
import {bindWatches} from "/js/watches.js";
import {bindTools} from "/js/tools.js";

function setStatus(label) {
  document.documentElement.dataset.status = label;
  const text = document.getElementById("status-text");
  if (text) {
    text.dataset.i18n = `header.${label}`;
    text.textContent = t(`header.${label}`);
  }
}

async function probeBroker() {
  try {
    const h = await fetchHealth();
    setStatus("connected");
    const versionEl = document.querySelector('[data-bind="version"]');
    if (versionEl && h?.version) versionEl.textContent = `v${h.version}`;
  } catch (_err) {
    setStatus("disconnected");
  }
}

function handleDashboardChatRequest(evt) {
  const msg = evt?.data?.message;
  if (typeof msg !== "string" || !msg) return;
  submitMessage(msg);
  flashTabTitle();
  desktopNotify(msg);
}

/** A simple multiplexer so each panel can subscribe to events. */
function makeBroker() {
  const handlers = new Set();
  return {
    on(fn) {
      handlers.add(fn);
      return () => handlers.delete(fn);
    },
    emit(evt) {
      for (const h of handlers) {
        try {
          h(evt);
        } catch (err) {
          console.warn("event handler threw", err);
        }
      }
    },
  };
}

function init() {
  document.documentElement.lang = getLang();
  applyTranslations();
  setStatus("connecting");

  document.getElementById("lang-toggle")?.addEventListener("click", () => {
    setLang(getLang() === "zh" ? "en" : "zh");
  });

  document.getElementById("timeline-clear")?.addEventListener("click", clearTimeline);

  bindTabs("activity");
  bindChat({formId: "chat-form", inputId: "chat-input", logId: "chat-log"});
  bindSettings({
    toggleId: "settings-toggle",
    drawerId: "settings-drawer",
    formId: "settings-form",
  });

  const evtBroker = makeBroker();
  bindScans({onEvent: evtBroker.on});
  bindWatches({onEvent: evtBroker.on});
  bindTools({onEvent: evtBroker.on});

  probeBroker();

  openEventStream({
    onOpen: () => setStatus("connected"),
    onClose: () => setStatus("disconnected"),
    onEvent: (evt) => {
      if (evt?.kind === "dashboard_chat_request") {
        handleDashboardChatRequest(evt);
        return;
      }
      // Activity timeline gets every event; specialized panels filter on kind.
      appendEventRow(evt);
      evtBroker.emit(evt);
    },
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, {once: true});
} else {
  init();
}
