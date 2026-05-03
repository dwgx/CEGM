/**
 * @file Thin wrapper over the broker's REST endpoints. Keeps URL paths in
 * one place and applies a uniform error contract: every function returns
 * the parsed JSON or throws an `Error` whose `.cause` is the underlying
 * fetch failure / non-2xx response body.
 */

const HEADERS_JSON = {"Content-Type": "application/json"};

async function jsonFetch(path, init = {}) {
  const res = await fetch(path, init);
  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch { /* empty / non-JSON */ }
    const err = new Error(`HTTP ${res.status} ${res.statusText} on ${path}`);
    err.cause = body;
    throw err;
  }
  return res.json();
}

/** GET /api/health → broker liveness + version. */
export function fetchHealth() {
  return jsonFetch("/api/health");
}

/** GET /api/config → sanitized config (no secrets). */
export function fetchConfig() {
  return jsonFetch("/api/config");
}

/** PUT /api/config — merge the given partial settings. */
export function updateConfig(partial) {
  return jsonFetch("/api/config", {
    method: "PUT",
    headers: HEADERS_JSON,
    body: JSON.stringify(partial),
  });
}

/**
 * POST /api/chat — send a user message. Server responds with an SSE stream
 * of assistant tokens + tool events. Returns the raw `Response` so the
 * caller can iterate `body.getReader()` chunks.
 */
export function postChat(messages) {
  return fetch("/api/chat", {
    method: "POST",
    headers: HEADERS_JSON,
    body: JSON.stringify({messages}),
  });
}
