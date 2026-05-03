/**
 * @file Renders incoming events as rows in the activity timeline.
 *
 * Event shape (from broker, see docs/TOOL_SPEC.md §"Events on the WebSocket"):
 *   { ts, id, kind, data }
 *
 * Rendering for Phase 1 is intentionally minimal — one row per event with a
 * timestamp, a tag for the event kind, and a JSON-stringified payload.
 * Phase 2 layers diff highlighting and expandable details on top.
 */
import {t} from "/js/i18n.js";

const TIMELINE_ID = "timeline";
const MAX_ROWS = 500;

const KIND_COLORS = {
  tool_called:        "text-sky-400",
  tool_result:        "text-emerald-400",
  tool_error:         "text-red-400",
  chat_user:          "text-zinc-300",
  chat_assistant:     "text-zinc-200",
  chat_token:         "text-zinc-500",
  preview_pending:    "text-amber-400",
  preview_committed:  "text-emerald-300",
  preview_canceled:   "text-zinc-500",
  snapshot_taken:     "text-violet-400",
  snapshot_restored:  "text-violet-300",
  broker_status:      "text-zinc-500",
  ce_status:          "text-zinc-500",
  dashboard_chat_request: "text-fuchsia-400",
};

function timelineEl() {
  return document.getElementById(TIMELINE_ID);
}

function formatTime(iso) {
  const m = iso.match(/T(\d\d:\d\d:\d\d\.\d{3})/);
  return m ? m[1] : iso;
}

/** Append one event to the timeline; trim oldest rows past MAX_ROWS. */
export function appendEventRow(evt) {
  const list = timelineEl();
  if (!list) return;

  // First real event clears the placeholder row.
  const first = list.firstElementChild;
  if (first?.dataset?.i18n === "activity.empty") {
    list.replaceChildren();
  }

  const li = document.createElement("li");
  li.className = "border-l-2 border-zinc-800 pl-3 py-1 break-words";

  const head = document.createElement("div");
  head.className = "flex items-baseline gap-2";

  const ts = document.createElement("span");
  ts.className = "text-zinc-500";
  ts.textContent = formatTime(evt.ts ?? new Date().toISOString());

  const kind = document.createElement("span");
  kind.className = (KIND_COLORS[evt.kind] ?? "text-zinc-300") + " uppercase";
  kind.textContent = evt.kind ?? "event";

  head.append(ts, kind);

  const body = document.createElement("pre");
  body.className = "mt-0.5 whitespace-pre-wrap text-zinc-400";
  body.textContent = JSON.stringify(evt.data ?? {}, null, 2);

  li.append(head, body);
  list.append(li);

  while (list.childElementCount > MAX_ROWS) {
    list.firstElementChild?.remove();
  }
  list.scrollTop = list.scrollHeight;
}

export function clearTimeline() {
  const list = timelineEl();
  if (!list) return;
  list.replaceChildren();
  const placeholder = document.createElement("li");
  placeholder.className = "text-zinc-600";
  placeholder.dataset.i18n = "activity.empty";
  placeholder.textContent = t("activity.empty");
  list.append(placeholder);
}
