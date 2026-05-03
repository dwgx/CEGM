/**
 * @file Chat UI wiring with Server-Sent Events streaming.
 *
 * Posts messages to `/api/chat`, reads the response body as an SSE stream,
 * and incrementally updates a single assistant bubble as `token` events
 * arrive. Tool calls are not rendered here (the activity timeline already
 * shows them via the `/events` WebSocket).
 *
 * Exposes :func:`submitMessage` so non-form drivers (e.g. the
 * ``dashboard_chat_request`` event handler) can inject a chat turn from
 * outside the form's submit flow.
 */
import {postChat} from "/js/api.js";
import {t} from "/js/i18n.js";

let _drivers = null;

/**
 * @param {{formId: string, inputId: string, logId: string}} ids
 */
export function bindChat(ids) {
  const form = document.getElementById(ids.formId);
  const input = /** @type {HTMLTextAreaElement | null} */ (document.getElementById(ids.inputId));
  const log = document.getElementById(ids.logId);
  if (!form || !input || !log) return;

  /** Append and return a chat row element so the caller can mutate it. */
  function appendMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className =
      role === "user"
        ? "self-end max-w-[85%] rounded-2xl bg-emerald-700/20 px-4 py-2 text-sm whitespace-pre-wrap"
        : "self-start max-w-[85%] rounded-2xl bg-zinc-800/80 px-4 py-2 text-sm whitespace-pre-wrap";
    wrap.textContent = text;

    if (log.firstElementChild?.tagName === "P") log.replaceChildren();

    log.append(wrap);
    log.scrollTop = log.scrollHeight;
    return wrap;
  }

  /** Iterate parsed SSE events from a fetch Response body. */
  async function* readSseEvents(res) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});

      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);

        const dataLines = frame
          .split("\n")
          .filter((l) => l.startsWith("data: "))
          .map((l) => l.slice(6));
        if (dataLines.length === 0) continue;
        const payload = dataLines.join("\n");
        if (payload === "[DONE]") return;
        try {
          yield JSON.parse(payload);
        } catch (err) {
          console.warn("ws: bad SSE payload", err, payload);
        }
      }
    }
  }

  function setBusy(busy) {
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.toggleAttribute("disabled", busy);
    input.toggleAttribute("disabled", busy);
  }

  /** The shared send pipeline used by both the form and ``submitMessage``. */
  async function send(text) {
    if (!text || !text.trim()) return;
    appendMessage("user", text);
    setBusy(true);

    let assistantEl = null;
    try {
      const res = await postChat([{role: "user", content: text}]);
      if (!res.ok) {
        let detail = "";
        let isApiKey = false;
        try {
          const j = await res.json();
          if (j?.error) {
            detail = ": " + j.error;
            isApiKey = String(j.error).toLowerCase().includes("api_key");
          }
        } catch {
          /* ignore */
        }
        appendMessage("assistant", t("chat.http_error", res.status, detail));
        if (isApiKey) appendMessage("assistant", t("chat.no_api_key_hint"));
        return;
      }

      for await (const evt of readSseEvents(res)) {
        if (evt.type === "token") {
          if (!assistantEl) assistantEl = appendMessage("assistant", "");
          assistantEl.textContent += evt.text;
          log.scrollTop = log.scrollHeight;
        } else if (evt.type === "error") {
          appendMessage("assistant", t("chat.stream_error", evt.error));
        }
        // tool_call / tool_result / tool_error / done are ignored here;
        // they show up on the activity timeline via the WebSocket.
      }

      if (!assistantEl) appendMessage("assistant", t("chat.no_response"));
    } catch (err) {
      appendMessage("assistant", t("chat.network_error", err.message));
    } finally {
      setBusy(false);
      input.focus();
    }
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
    await send(text);
  });

  _drivers = {send};
}

/**
 * Inject a user message programmatically. Used by the
 * ``dashboard_chat_request`` event handler so an external MCP client
 * can hand off a conversation to the dashboard.
 */
export function submitMessage(text) {
  if (!_drivers) {
    console.warn("submitMessage called before bindChat");
    return;
  }
  _drivers.send(text);
}
