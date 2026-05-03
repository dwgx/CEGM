"""WebSocket endpoint at ``/events``.

Subscribes the connected client to the broker's :class:`EventBus` and
forwards every event as a JSON frame. Clients reconnect automatically
(see ``web/js/ws.js``) so we do nothing special on disconnect — the
subscription auto-cleans via the ``subscribe()`` context manager.

On connect we replay the most recent ~50 events so a freshly-loaded
dashboard tab catches up on the session without polling
``/api/health`` or the ``cegm.activity_recent`` resource.
"""

from __future__ import annotations

import contextlib

from starlette.websockets import WebSocket, WebSocketDisconnect

from cegm_broker._logging import get_logger
from cegm_broker.event_bus import EventBus

_log = get_logger(__name__)

# Number of historical events to replay on connect.
_REPLAY_LIMIT = 50


async def events_endpoint(websocket: WebSocket) -> None:
    """ASGI WebSocket handler — install with ``WebSocketRoute``."""
    bus: EventBus = websocket.app.state.bus
    await websocket.accept()
    _log.info("ws.connected", extra={"subscribers_after": bus.subscriber_count + 1})

    try:
        # Subscribe BEFORE replaying so events published in the gap between
        # the two operations land on our queue rather than being dropped.
        async with bus.subscribe() as stream:
            for past in bus.recent(_REPLAY_LIMIT):
                await websocket.send_json(past)
            async for event in stream:
                await websocket.send_json(event)
    except WebSocketDisconnect:
        _log.info("ws.disconnected")
    except Exception as exc:
        _log.warning("ws.error", extra={"err": repr(exc)})
        with contextlib.suppress(Exception):
            await websocket.close()
