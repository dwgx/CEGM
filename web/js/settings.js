/**
 * @file Settings drawer wiring. Loads sanitized config on open, posts
 * partial updates on submit. Keeps the form state-synced with the broker
 * so reloading the page doesn't lose unsaved typing.
 */
import {fetchConfig, updateConfig} from "/js/api.js";

/**
 * @param {{toggleId: string, drawerId: string, formId: string}} ids
 */
export function bindSettings(ids) {
  const toggle = document.getElementById(ids.toggleId);
  const drawer = document.getElementById(ids.drawerId);
  const form = /** @type {HTMLFormElement | null} */ (document.getElementById(ids.formId));
  if (!toggle || !drawer || !form) return;

  async function open() {
    drawer.hidden = false;
    try {
      const cfg = await fetchConfig();
      // Hydrate form fields. Server-side `api_key` field comes back masked
      // ("***") if a key is set; we keep the field empty so the user can
      // see whether they need to re-enter it.
      const llm = cfg?.llm ?? {};
      form.elements.namedItem("base_url").value = llm.base_url ?? "";
      form.elements.namedItem("model").value = llm.model ?? "";
      form.elements.namedItem("api_key").value = "";
      form.elements.namedItem("api_key").placeholder = llm.api_key === "***" ? "(unchanged)" : "sk-…";

      const safety = cfg?.safety ?? {};
      const cb = form.elements.namedItem("preview_writes_default");
      if (cb instanceof HTMLInputElement) cb.checked = Boolean(safety.preview_writes_default);
    } catch {
      // Broker not up yet; user can still edit, save will retry.
    }
  }

  function close() {
    drawer.hidden = true;
  }

  toggle.addEventListener("click", () => (drawer.hidden ? open() : close()));
  drawer.querySelector("[data-close-drawer]")?.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !drawer.hidden) close();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const partial = {
      llm: {
        base_url: fd.get("base_url") || undefined,
        model: fd.get("model") || undefined,
      },
      safety: {
        preview_writes_default: fd.get("preview_writes_default") === "on",
      },
    };
    const apiKey = (fd.get("api_key") ?? "").toString();
    if (apiKey) partial.llm.api_key = apiKey;

    try {
      await updateConfig(partial);
      close();
    } catch (err) {
      console.error("settings save failed", err);
    }
  });
}
