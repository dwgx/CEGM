/**
 * @file Dashboard entry point. Wires DOM event handlers to the modular
 * subsystems (api / ws / timeline / chat / settings) and kicks off the
 * WebSocket connection.
 *
 * Each subsystem is intentionally a small self-contained module with no
 * dependency on a framework. Phase 5 may pull in Solid or Preact once the
 * feature surface justifies it.
 */
import {fetchHealth} from "/js/api.js";
import {openEventStream} from "/js/ws.js";
import {appendEventRow, clearTimeline} from "/js/timeline.js";
import {bindChat} from "/js/chat.js";
import {bindSettings} from "/js/settings.js";

/** Update the connection-status pill. */
function setStatus(label) {
  document.documentElement.dataset.status = label;
  const text = document.getElementById("status-text");
  if (text) text.textContent = label;
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

function init() {
  setStatus("connecting");

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

  // Initial liveness probe; the WebSocket will keep status updated thereafter.
  probeBroker();

  openEventStream({
    onOpen: () => setStatus("connected"),
    onClose: () => setStatus("disconnected"),
    onEvent: (evt) => appendEventRow(evt),
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, {once: true});
} else {
  init();
}
