/**
 * @file Browser-side attention helpers — flash the tab title while the
 * page is in the background, and (best-effort) raise a desktop
 * notification when permitted. Used by the dashboard_chat_request flow
 * so an external MCP client handing off to the dashboard can grab the
 * user's attention.
 */
import {t} from "/js/i18n.js";

let _flashing = false;
let _origTitle = "";

/**
 * Prefix the document title with a bell until the tab regains focus.
 * No-op if already flashing or the tab is currently visible.
 */
export function flashTabTitle() {
  if (_flashing) return;
  if (!document.hidden) return;  // already in foreground — no need
  _flashing = true;
  _origTitle = document.title;

  let shown = true;
  const tick = setInterval(() => {
    document.title = shown ? _origTitle : "● " + _origTitle;
    shown = !shown;
  }, 1000);

  function stop() {
    if (!_flashing) return;
    _flashing = false;
    clearInterval(tick);
    document.title = _origTitle;
    document.removeEventListener("visibilitychange", onVis);
  }
  function onVis() {
    if (!document.hidden) stop();
  }
  document.addEventListener("visibilitychange", onVis);
}

/**
 * Best-effort desktop notification. Silently no-ops if permission is
 * denied; lazily prompts on first use.
 */
export async function desktopNotify(body) {
  if (!("Notification" in window)) return;
  let permission = Notification.permission;
  if (permission === "default") {
    try {
      permission = await Notification.requestPermission();
    } catch {
      return;
    }
  }
  if (permission !== "granted") return;
  try {
    new Notification(t("notify.title"), {
      body: t("notify.body_prefix") + body,
      icon: "/favicon.ico",
      tag: "cegm-dashboard-chat",
    });
  } catch (err) {
    console.warn("notification failed", err);
  }
}
