/**
 * @file WebSocket client for the broker's `/events` stream.
 *
 * Auto-reconnects with exponential back-off. Hands every received frame
 * (parsed as JSON) to the user-supplied `onEvent` callback. Connection
 * lifecycle hooks (`onOpen`, `onClose`) drive the header status pill.
 */

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 30_000;

/**
 * @param {{onOpen?: () => void, onClose?: () => void, onEvent: (e: object) => void}} hooks
 * @returns {{close: () => void}}
 */
export function openEventStream(hooks) {
  let attempts = 0;
  let closed = false;
  let socket = null;

  function url() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/events`;
  }

  function connect() {
    socket = new WebSocket(url());

    socket.addEventListener("open", () => {
      attempts = 0;
      hooks.onOpen?.();
    });

    socket.addEventListener("message", (msg) => {
      let payload;
      try { payload = JSON.parse(msg.data); }
      catch (e) { console.warn("ws: non-JSON frame", e); return; }
      hooks.onEvent(payload);
    });

    socket.addEventListener("close", () => {
      hooks.onClose?.();
      if (!closed) scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      // close handler will run; let it do the reconnect math.
    });
  }

  function scheduleReconnect() {
    attempts += 1;
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** (attempts - 1), RECONNECT_MAX_MS);
    setTimeout(connect, delay);
  }

  connect();
  return {
    close() {
      closed = true;
      socket?.close();
    },
  };
}
