/**
 * @file Chat UI wiring. Phase 1 implementation streams from `/api/chat`
 * via SSE; this scaffold renders user input and sets up the form
 * lifecycle so subsequent patches can plug streaming in.
 */
import {postChat} from "/js/api.js";

/**
 * @param {{formId: string, inputId: string, logId: string}} ids
 */
export function bindChat(ids) {
  const form = document.getElementById(ids.formId);
  const input = /** @type {HTMLTextAreaElement | null} */ (document.getElementById(ids.inputId));
  const log = document.getElementById(ids.logId);
  if (!form || !input || !log) return;

  /** Append a chat row. */
  function appendMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className =
      role === "user"
        ? "self-end max-w-[85%] rounded-2xl bg-emerald-700/20 px-4 py-2 text-sm"
        : "self-start max-w-[85%] rounded-2xl bg-zinc-800/80 px-4 py-2 text-sm";
    wrap.textContent = text;

    // First-message ergonomics: clear the placeholder paragraph.
    if (log.firstElementChild?.tagName === "P") log.replaceChildren();

    log.append(wrap);
    log.scrollTop = log.scrollHeight;
  }

  // Submit on Enter (without Shift) — newline on Shift+Enter.
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    appendMessage("user", text);

    try {
      // Phase 1 will iterate the SSE stream and append assistant tokens.
      const res = await postChat([{role: "user", content: text}]);
      if (!res.ok) {
        appendMessage("assistant", `(error: HTTP ${res.status})`);
        return;
      }
      const body = await res.text();
      appendMessage("assistant", body || "(no response yet — Phase 1 implementation pending)");
    } catch (err) {
      appendMessage("assistant", `(network error: ${err.message})`);
    }
  });
}
