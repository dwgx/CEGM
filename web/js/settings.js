/**
 * @file Settings drawer wiring. Loads sanitized config on open, posts
 * partial updates on submit. Keeps the form state-synced with the broker
 * so reloading the page doesn't lose unsaved typing.
 */
import {fetchConfig, updateConfig} from "/js/api.js";
import {t} from "/js/i18n.js";

/**
 * @param {{toggleId: string, drawerId: string, formId: string}} ids
 */
export function bindSettings(ids) {
  const toggle = document.getElementById(ids.toggleId);
  const drawer = document.getElementById(ids.drawerId);
  const form = /** @type {HTMLFormElement | null} */ (document.getElementById(ids.formId));
  if (!toggle || !drawer || !form) return;

  /** Hydrate the form from the broker's current config. */
  async function hydrate() {
    try {
      const cfg = await fetchConfig();

      const llm = cfg?.llm ?? {};
      form.elements.namedItem("base_url").value = llm.base_url ?? "";
      form.elements.namedItem("model").value = llm.model ?? "";
      form.elements.namedItem("api_key").value = "";
      form.elements.namedItem("api_key").placeholder =
        llm.api_key === "***" ? t("settings.api_key_unchanged") : t("settings.api_key_placeholder");

      const ui = cfg?.ui ?? {};
      const showForm = form.elements.namedItem("show_status_form");
      if (showForm instanceof HTMLInputElement) {
        showForm.checked = ui.show_status_form !== false;
      }

      const safety = cfg?.safety ?? {};
      const cb = form.elements.namedItem("preview_writes_default");
      if (cb instanceof HTMLInputElement) cb.checked = Boolean(safety.preview_writes_default);

      const mcpUrl = `${location.origin}/mcp`;
      const mcpInput = /** @type {HTMLInputElement | null} */ (
        document.getElementById("mcp-url")
      );
      if (mcpInput) mcpInput.value = mcpUrl;
    } catch {
      // Broker not up yet; user can still edit, save will retry.
    }
  }

  async function open() {
    drawer.hidden = false;
    await hydrate();
  }

  function close() {
    drawer.hidden = true;
  }

  toggle.addEventListener("click", () => (drawer.hidden ? open() : close()));
  drawer.querySelector("[data-close-drawer]")?.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !drawer.hidden) close();
  });

  document.getElementById("mcp-url-copy")?.addEventListener("click", async () => {
    const input = /** @type {HTMLInputElement | null} */ (document.getElementById("mcp-url"));
    if (!input) return;
    const url = input.value;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      input.select();
      document.execCommand("copy");
      input.setSelectionRange(0, 0);
    }
    flashCopied(input);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    /** @type {Record<string, any>} */
    const partial = {
      llm: {
        base_url: fd.get("base_url") || undefined,
        model: fd.get("model") || undefined,
      },
      safety: {
        preview_writes_default: fd.get("preview_writes_default") === "on",
      },
      ui: {
        show_status_form: fd.get("show_status_form") === "on",
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

/** Briefly flash the i18n "Copied!" hint in the URL field. */
function flashCopied(target) {
  const original = target.value;
  target.value = t("settings.copied");
  target.classList.add("text-emerald-400");
  setTimeout(() => {
    target.value = original;
    target.classList.remove("text-emerald-400");
  }, 800);
}
