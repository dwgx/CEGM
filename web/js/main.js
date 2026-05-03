/**
 * @file Dashboard entry point. Wires DOM event handlers to the modular
 * subsystems (api / ws / timeline / chat / settings / i18n / notify) and
 * kicks off the WebSocket connection.
 */
import {fetchHealth} from "/js/api.js";
import {openEventStream} from "/js/ws.js";
import {appendEventRow, clearTimeline} from "/js/timeline.js";
import {bindChat, submitMessage} from "/js/chat.js";
import {bindSettings} from "/js/settings.js";
import {applyTranslations, getLang, setLang, t} from "/js/i18n.js";
import {flashTabTitle, desktopNotify} from "/js/notify.js";

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

/**
 * An external MCP client called ``cegm.dashboard_chat`` and the broker
 * fanned out a ``dashboard_chat_request`` event. Inject the message
 * into the local chat as if the user had typed it, flash the tab
 * title, and try to raise a desktop notification.
 */
function handleDashboardChatRequest(evt) {
  const msg = evt?.data?.message;
  if (typeof msg !== "string" || !msg) return;
  submitMessage(msg);
  flashTabTitle();
  desktopNotify(msg);
}

function init() {
  // Apply translations BEFORE binding so labels rendered by JS
  // (e.g. status text) pick up the right locale.
  document.documentElement.lang = getLang();
  applyTranslations();
  setStatus("connecting");

  document.getElementById("lang-toggle")?.addEventListener("click", () => {
    setLang(getLang() === "zh" ? "en" : "zh");
  });

  document.getElementById("timeline-clear")?.addEventListener("click", clearTimeline);

  bindChat({
    formId: "chat-form",
    inputId: "chat-input",
    logId: "chat-log",
  });

  bindSettings({
    toggleId: "settings-toggle",
    drawerId: "settings-drawer",
    formId: "settings-form",
  });

  probeBroker();

  openEventStream({
    onOpen: () => setStatus("connected"),
    onClose: () => setStatus("disconnected"),
    onEvent: (evt) => {
      // External-client → dashboard hand-off: don't render in timeline,
      // run the chat injection instead.
      if (evt?.kind === "dashboard_chat_request") {
        handleDashboardChatRequest(evt);
        return;
      }
      appendEventRow(evt);
    },
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, {once: true});
} else {
  init();
}
