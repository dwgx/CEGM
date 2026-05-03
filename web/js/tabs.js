/**
 * @file Tab switching for the right rail. Buttons with
 * ``data-tab="<key>"`` toggle visibility of panels with
 * ``data-tab-panel="<key>"``. The active button gets the
 * ``aria-selected="true"`` + ``data-active`` markers; panels are
 * shown/hidden via the ``hidden`` attribute (which our CSS
 * forces ``display: none !important`` on).
 */

const STORAGE_KEY = "cegm-active-tab";

/** Activate the tab with the given key. Persists choice. */
export function activateTab(key) {
  const buttons = document.querySelectorAll("[data-tab]");
  const panels = document.querySelectorAll("[data-tab-panel]");
  let matched = false;
  for (const btn of buttons) {
    const isActive = btn.dataset.tab === key;
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
    if (isActive) {
      btn.dataset.active = "true";
      matched = true;
    } else {
      delete btn.dataset.active;
    }
  }
  for (const p of panels) {
    p.hidden = p.dataset.tabPanel !== key;
  }
  if (matched) localStorage.setItem(STORAGE_KEY, key);
}

/** Bind clicks + restore previous selection (or fall back to ``defaultKey``). */
export function bindTabs(defaultKey = "activity") {
  for (const btn of document.querySelectorAll("[data-tab]")) {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
  }
  const saved = localStorage.getItem(STORAGE_KEY);
  activateTab(saved || defaultKey);
}
