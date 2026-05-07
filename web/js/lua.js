/**
 * @file Lua Sandbox — execute Lua snippets inside Cheat Engine.
 */

async function callMcp(name, args) {
  const res = await fetch("/mcp", {
    method: "POST",
    headers: {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    body: JSON.stringify({jsonrpc: "2.0", id: Date.now(), method: "tools/call", params: {name, arguments: args}}),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function appendOutput(text, level) {
  const out = document.getElementById("lua-output");
  if (!out) return;
  if (out.firstChild?.textContent === "Output appears here…") out.innerHTML = "";
  const div = document.createElement("div");
  div.style.cssText = `padding:2px 0;border-bottom:1px solid hsl(var(--border));color:${
    level === "error" ? "hsl(var(--destructive))" : level === "result" ? "hsl(var(--success))" : "hsl(var(--muted-foreground))"
  }`;
  div.textContent = text;
  out.append(div);
  out.scrollTop = out.scrollHeight;
}

export function bindLua() {
  const editor = document.getElementById("lua-editor");
  const runBtn = document.getElementById("lua-run");
  const clearBtn = document.getElementById("lua-clear");
  const output = document.getElementById("lua-output");

  if (!editor || !runBtn) return;

  // Ctrl+Enter to run
  editor.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      runBtn.click();
    }
  });

  runBtn.addEventListener("click", async () => {
    const code = editor.value.trim();
    if (!code) return;
    appendOutput(`> ${code.slice(0, 80)}${code.length > 80 ? "…" : ""}`, "info");
    runBtn.disabled = true;
    try {
      const j = await callMcp("cegm.lua_eval", {code});
      const result = j?.result?.content?.[0]?.text;
      if (result) {
        try {
          const parsed = JSON.parse(result);
          appendOutput(JSON.stringify(parsed, null, 2), "result");
        } catch {
          appendOutput(result, "result");
        }
      } else {
        appendOutput(JSON.stringify(j), "result");
      }
    } catch (err) {
      appendOutput(`Error: ${err.message}`, "error");
    } finally {
      runBtn.disabled = false;
    }
  });

  clearBtn?.addEventListener("click", () => {
    if (output) output.innerHTML = "Output appears here…";
  });
}
