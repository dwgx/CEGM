/**
 * @file Hex Viewer — memory hex dump with navigation.
 */

let _currentAddr = "";
let _currentLen = 128;

async function callMcp(name, args) {
  const res = await fetch("/mcp", {
    method: "POST",
    headers: {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    body: JSON.stringify({jsonrpc: "2.0", id: Date.now(), method: "tools/call", params: {name, arguments: args}}),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const j = await res.json();
  return j?.result?.content?.[0]?.text;
}

function parseHexOffset(addr) {
  if (!addr) return null;
  // Handle "module.exe+0x1234" style
  const m = addr.match(/\+0x([0-9a-fA-F]+)$/);
  if (m) return parseInt(m[1], 16);
  // Handle plain hex
  const h = addr.match(/^0x([0-9a-fA-F]+)$/);
  if (h) return parseInt(h[1], 16);
  return null;
}

function adjustAddr(addr, delta) {
  const off = parseHexOffset(addr);
  if (off !== null) {
    const m = addr.match(/^(.+?)\+0x/);
    if (m) return `${m[1]}+0x${(off + delta).toString(16).toUpperCase()}`;
    return `0x${(off + delta).toString(16).toUpperCase()}`;
  }
  return addr;
}

async function readAndRender() {
  const addrEl = document.getElementById("hex-addr");
  const lenEl = document.getElementById("hex-len");
  const out = document.getElementById("hex-output");
  if (!addrEl || !out) return;

  const addr = addrEl.value.trim();
  const len = parseInt(lenEl?.value || "128");
  if (!addr) return;

  _currentAddr = addr;
  _currentLen = len;

  out.textContent = "Reading…";
  try {
    const raw = await callMcp("cegm.hex_dump", {address: addr, length: len});
    const data = JSON.parse(raw || "{}");
    const rows = data.rows || [];
    if (!rows.length) {
      out.textContent = `No data at ${addr}`;
      return;
    }
    let text = `HEX DUMP  ${addr}  (${data.length || len} bytes)\n`;
    text += `${"─".repeat(68)}\n`;
    text += "OFFSET   00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F  ┊ ASCII\n";
    text += `${"─".repeat(68)}\n`;
    for (const row of rows) {
      const offHex = (row.offset || 0).toString(16).toUpperCase().padStart(8, "0");
      text += `${offHex}  ${(row.hex || "").padEnd(47)} ┊ ${row.ascii || ""}\n`;
    }
    out.textContent = text;
  } catch (err) {
    out.textContent = `Error: ${err.message}`;
  }
}

export function bindHex() {
  document.getElementById("hex-read")?.addEventListener("click", readAndRender);
  document.getElementById("hex-addr")?.addEventListener("keydown", (e) => { if (e.key === "Enter") readAndRender(); });

  const nav = (delta) => () => {
    const el = document.getElementById("hex-addr");
    if (el) { el.value = adjustAddr(_currentAddr || el.value, delta); readAndRender(); }
  };
  document.getElementById("hex-nav-up16")?.addEventListener("click", nav(-16));
  document.getElementById("hex-nav-up64")?.addEventListener("click", nav(-64));
  document.getElementById("hex-nav-dn64")?.addEventListener("click", nav(64));
  document.getElementById("hex-nav-dn16")?.addEventListener("click", nav(16));
}
