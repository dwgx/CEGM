/**
 * @file Settings drawer. Loads sanitized config on open, saves on submit.
 */
import {fetchConfig, updateConfig} from "/js/api.js";

export function bindSettings({toggleId, drawerId, formId, closeId}) {
  const toggle = document.getElementById(toggleId);
  const drawer = document.getElementById(drawerId);
  const form = document.getElementById(formId);
  const closeBtn = document.getElementById(closeId);
  if (!toggle || !drawer || !form) return;

  async function hydrate() {
    try {
      const cfg = await fetchConfig();
      const llm = cfg?.llm ?? {};
      form.elements.namedItem("base_url").value = llm.base_url ?? "";
      form.elements.namedItem("model").value = llm.model ?? "";
      form.elements.namedItem("api_key").value = "";
      form.elements.namedItem("api_key").placeholder = llm.api_key === "***" ? "(unchanged)" : "sk-…";
      const safety = cfg?.safety ?? {};
      const cb = form.elements.namedItem("preview_writes_default");
      if (cb instanceof HTMLInputElement) cb.checked = Boolean(safety.preview_writes_default);
    } catch (_) {}
  }

  function open() { drawer.hidden = false; hydrate(); }
  function close() { drawer.hidden = true; }

  toggle.addEventListener("click", () => (drawer.hidden ? open() : close()));
  closeBtn?.addEventListener("click", close);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !drawer.hidden) close(); });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const partial = {
      llm: { base_url: fd.get("base_url") || undefined, model: fd.get("model") || undefined },
      safety: { preview_writes_default: fd.get("preview_writes_default") === "on" },
    };
    const apiKey = (fd.get("api_key") ?? "").toString();
    if (apiKey) partial.llm.api_key = apiKey;
    try { await updateConfig(partial); close(); } catch (err) { console.error("settings save failed", err); }
  });
}
