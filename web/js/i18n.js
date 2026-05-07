/**
 * @file Tiny in-house i18n. No framework, no build step. The full
 * translation table lives in this file; UI elements opt-in by carrying
 * a ``data-i18n="key"`` (or ``data-i18n-placeholder="key"``,
 * ``data-i18n-title="key"``) attribute. Dynamic strings produced by JS
 * call ``t("key", subs)`` directly.
 *
 * Two locales for now: ``en`` and ``zh``. The chosen language persists
 * to ``localStorage["cegm-lang"]``; the toggle lives in the header.
 */

const STRINGS = {
  en: {
    "header.connected": "CONNECTED",
    "header.disconnected": "DISCONNECTED",
    "header.connecting": "CONNECTING",
    "header.settings": "Settings",
    "header.lang_toggle": "中文",
    "header.lang_toggle_title": "Switch to Chinese",

    "chat.placeholder": "Ask the model to find / read / write memory…",
    "chat.send": "Send",
    "chat.welcome":
      "Type a message below. Tool calls run against Cheat Engine and show on the timeline as they happen.",
    "chat.no_response": "(no response)",
    "chat.network_error": "(network error: %s)",
    "chat.stream_error": "(stream error: %s)",
    "chat.http_error": "(error: HTTP %s%s)",
    "chat.no_api_key_hint":
      "Tip: open Settings → save a DeepSeek API key, then retry.",

    "sidebar.navigate": "Navigate",
    "sidebar.tools": "Tools",
    "sidebar.inspect": "Inspect",
    "tabs.workspace": "Workspace",
    "tabs.chat": "Chat",
    "tabs.lua": "Lua",
    "tabs.hex": "Hex",
    "tabs.activity": "Activity",
    "tabs.scans": "Scans",
    "tabs.watches": "Watches",
    "tabs.timeline": "Timeline",
    "tabs.tools": "Tools",

    "activity.clear": "clear",
    "activity.empty": "— no activity yet —",

    "scans.empty": "— no scans yet — call cegm.scan or use the chat —",
    "scans.count_label": "hits",
    "scans.narrow": "Narrow",
    "scans.drop": "Drop",
    "scans.narrowed_from": "narrowed from",

    "watches.empty": "— no watches yet — call cegm.watch_add —",
    "watches.address": "Address",
    "watches.value": "Value",
    "watches.label": "Label",
    "watches.last_seen": "Last seen",
    "watches.remove": "Remove",
    "watches.actions": "Act",
    "watches.error": "Error",

    "tools.search_placeholder": "filter by name or description…",
    "tools.empty": "— loading tool list —",
    "tools.refresh": "refresh",
    "tools.cat_cegm": "CEGM",
    "tools.cat_custom": "Custom",
    "tools.cat_scan": "Scan",
    "tools.cat_memory": "Memory",
    "tools.cat_aob": "AOB",
    "tools.cat_pointer": "Pointer",
    "tools.cat_breakpoint": "Breakpoint",
    "tools.cat_disasm": "Disasm",
    "tools.cat_lua": "Lua",
    "tools.cat_inject": "Inject",
    "tools.cat_cheat_table": "Cheat table",
    "tools.cat_other": "Other",

    "settings.title": "Settings",
    "settings.close": "Close",
    "settings.save": "Save",
    "settings.llm_endpoint": "LLM endpoint",
    "settings.base_url": "Base URL",
    "settings.api_key": "API key",
    "settings.api_key_placeholder": "sk-…",
    "settings.api_key_unchanged": "(unchanged)",
    "settings.model": "Model",
    "settings.mcp_endpoint": "MCP endpoint",
    "settings.mcp_blurb":
      "Point any MCP client (Claude Desktop, Cursor, Codex, Claude Code) at this URL. No per-host setup needed — as long as Cheat Engine is running, the URL is live.",
    "settings.copy": "Copy",
    "settings.copied": "Copied!",
    "settings.ce_ui": "Cheat Engine UI",
    "settings.show_form": "Show CEGM status window on Cheat Engine startup",
    "settings.show_form_hint":
      "Off by default. The broker is started either by the C plugin (Open CEGM Dashboard menu, silent) or by you running ``cegm-broker --port 27077`` manually. The Lua autorun does not spawn the broker.",
    "settings.safety": "Safety",
    "settings.preview_writes": "Preview every memory write before applying",

    "notify.title": "CEGM",
    "notify.body_prefix": "Incoming chat from MCP client: ",
  },
  zh: {
    "header.connected": "已连接",
    "header.disconnected": "已断开",
    "header.connecting": "连接中",
    "header.settings": "设置",
    "header.lang_toggle": "EN",
    "header.lang_toggle_title": "切换到英文",

    "chat.placeholder": "让模型帮你查找 / 读取 / 写入内存…",
    "chat.send": "发送",
    "chat.welcome":
      "在下方输入消息。工具调用会在 Cheat Engine 上跑、实时显示在右侧活动流。",
    "chat.no_response": "（无响应）",
    "chat.network_error": "（网络错误：%s）",
    "chat.stream_error": "（流式错误：%s）",
    "chat.http_error": "（错误：HTTP %s%s）",
    "chat.no_api_key_hint": "提示：打开 Settings → 保存一个 DeepSeek API key 后重试。",

    "sidebar.navigate": "导航",
    "sidebar.tools": "工具",
    "sidebar.inspect": "检查",
    "tabs.workspace": "工作区",
    "tabs.chat": "对话",
    "tabs.lua": "Lua",
    "tabs.hex": "Hex",
    "tabs.activity": "活动",
    "tabs.scans": "扫描",
    "tabs.watches": "监视",
    "tabs.timeline": "时间线",
    "tabs.tools": "工具",

    "activity.clear": "清空",
    "activity.empty": "— 暂无活动 —",

    "scans.empty": "— 暂无扫描 — 调用 cegm.scan 或在聊天框输入 —",
    "scans.count_label": "命中",
    "scans.narrow": "缩小",
    "scans.drop": "放弃",
    "scans.narrowed_from": "由此缩小自",

    "watches.empty": "— 暂无监视 — 调用 cegm.watch_add —",
    "watches.address": "地址",
    "watches.value": "值",
    "watches.label": "标签",
    "watches.last_seen": "最后变化",
    "watches.remove": "移除",
    "watches.actions": "操作",
    "watches.error": "错误",

    "tools.search_placeholder": "按名称或描述过滤…",
    "tools.empty": "— 加载工具列表中 —",
    "tools.refresh": "刷新",
    "tools.cat_cegm": "CEGM",
    "tools.cat_custom": "自定义",
    "tools.cat_scan": "扫描",
    "tools.cat_memory": "内存",
    "tools.cat_aob": "AOB",
    "tools.cat_pointer": "指针",
    "tools.cat_breakpoint": "断点",
    "tools.cat_disasm": "反汇编",
    "tools.cat_lua": "Lua",
    "tools.cat_inject": "注入",
    "tools.cat_cheat_table": "速查表",
    "tools.cat_other": "其他",

    "settings.title": "设置",
    "settings.close": "关闭",
    "settings.save": "保存",
    "settings.llm_endpoint": "LLM 端点",
    "settings.base_url": "Base URL",
    "settings.api_key": "API Key",
    "settings.api_key_placeholder": "sk-…",
    "settings.api_key_unchanged": "（保持不变）",
    "settings.model": "模型",
    "settings.mcp_endpoint": "MCP 端点",
    "settings.mcp_blurb":
      "把任意 MCP 客户端（Claude Desktop、Cursor、Codex、Claude Code）指向这个 URL。无需配置 — 只要 Cheat Engine 在跑，URL 就活。",
    "settings.copy": "复制",
    "settings.copied": "已复制！",
    "settings.ce_ui": "Cheat Engine 界面",
    "settings.show_form": "启动 Cheat Engine 时显示 CEGM 状态窗口",
    "settings.show_form_hint":
      "默认关闭。Broker 由 C 插件菜单「Open CEGM Dashboard」（静默拉起）或者你自己运行 ``cegm-broker --port 27077`` 启动。Lua autorun 不会自动起 broker。",
    "settings.safety": "安全",
    "settings.preview_writes": "每次内存写入前先预览",

    "notify.title": "CEGM",
    "notify.body_prefix": "来自 MCP 客户端的新消息：",
  },
};

const STORAGE_KEY = "cegm-lang";
const listeners = new Set();
let _lang = null;

/** Current language code. Defaults to browser language → ``en``. */
export function getLang() {
  if (_lang) return _lang;
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved && saved in STRINGS) {
    _lang = saved;
    return _lang;
  }
  const nav = (navigator.language || "en").toLowerCase();
  _lang = nav.startsWith("zh") ? "zh" : "en";
  return _lang;
}

/** Lookup, with optional ``%s`` substitutions in declaration order. */
export function t(key, ...subs) {
  const lang = getLang();
  const s = STRINGS[lang]?.[key] ?? STRINGS.en[key] ?? key;
  if (subs.length === 0) return s;
  let i = 0;
  return s.replace(/%s/g, () => {
    const v = subs[i];
    i += 1;
    return v == null ? "" : String(v);
  });
}

/** Switch the active language and re-render any DOM marked with data-i18n. */
export function setLang(lang) {
  if (!(lang in STRINGS)) return;
  _lang = lang;
  localStorage.setItem(STORAGE_KEY, lang);
  document.documentElement.lang = lang;
  applyTranslations();
  for (const fn of listeners) {
    try {
      fn(lang);
    } catch (err) {
      console.warn("i18n listener threw", err);
    }
  }
}

/** Subscribe to language changes. Returns an unsubscribe function. */
export function onLangChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Apply translations to every element carrying a ``data-i18n*`` attribute. */
export function applyTranslations(root = document) {
  for (const el of root.querySelectorAll("[data-i18n]")) {
    el.textContent = t(el.dataset.i18n);
  }
  for (const el of root.querySelectorAll("[data-i18n-placeholder]")) {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  }
  for (const el of root.querySelectorAll("[data-i18n-title]")) {
    el.title = t(el.dataset.i18nTitle);
  }
  for (const el of root.querySelectorAll("[data-i18n-aria-label]")) {
    el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel));
  }
}
