/**
 * @file Chat — SSE streaming chat with tool routing.
 */
import {postChat} from "/js/api.js";

let _drivers = null;

export function bindChat({formId, inputId, logId}) {
  const form = document.getElementById(formId);
  const input = document.getElementById(inputId);
  const log = document.getElementById(logId);
  if (!form || !input || !log) return;

  function appendMsg(role, text) {
    const div = document.createElement("div");
    div.className = "chat-msg " + role;
    div.textContent = text;
    log.append(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }

  async function* readSse(res) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      let sep;
      while ((sep = buf.indexOf("\n\n")) !== -1) {
        const frame = buf.slice(0, sep);
        buf = buf.slice(sep + 2);
        const lines = frame.split("\n").filter(l => l.startsWith("data: ")).map(l => l.slice(6));
        if (!lines.length) continue;
        const payload = lines.join("\n");
        if (payload === "[DONE]") return;
        try { yield JSON.parse(payload); } catch (_) {}
      }
    }
  }

  async function send(text) {
    if (!text || !text.trim()) return;
    appendMsg("user", text);
    input.value = "";

    let assistantEl = null;
    try {
      const res = await postChat([{role: "user", content: text}]);
      if (!res.ok) {
        let detail = ""; try { detail = ": " + (await res.json()).error; } catch (_) {}
        appendMsg("assistant", `Error: HTTP ${res.status}${detail}`);
        return;
      }
      for await (const evt of readSse(res)) {
        if (evt.type === "token") {
          if (!assistantEl) assistantEl = appendMsg("assistant", "");
          assistantEl.textContent += evt.text;
          log.scrollTop = log.scrollHeight;
        } else if (evt.type === "error") {
          appendMsg("assistant", `Stream error: ${evt.error}`);
        }
      }
      if (!assistantEl) appendMsg("assistant", "(no response)");
    } catch (err) {
      appendMsg("assistant", `Network error: ${err.message}`);
    }
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener("submit", async (e) => { e.preventDefault(); await send(input.value.trim()); });
  _drivers = {send};
}

export function submitMessage(text) { if (_drivers) _drivers.send(text); }
