"""CEGM-namespaced MCP tools layered over the proxied surface.

Phase 1 ships :func:`cegm.activity_recent` only — enough to prove the
extras pathway end-to-end. Snapshots and the preview-write triplet land
in Phase 2 / Phase 3. See :doc:`/docs/TOOL_SPEC.md`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Final

from mcp import types

from cegm_broker._logging import get_logger
from cegm_broker.event_bus import Event, EventBus

_log = get_logger(__name__)

EXTRAS_TOOL_DEFS: Final[list[types.Tool]] = [
    types.Tool(
        name="cegm.activity_recent",
        description=(
            "Return the most recent CEGM events (tool calls, chat turns, "
            "preview/snapshot lifecycle, broker/CE status). Use when you "
            "need to recall what just happened without re-running tools."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 50,
                    "description": "Max events to return (most recent last).",
                },
            },
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="cegm.dashboard_chat",
        description=(
            "Hand off a chat message to the CEGM browser dashboard. The "
            "broker broadcasts a 'dashboard_chat_request' event over its "
            "WebSocket so any open dashboard tab auto-submits the message "
            "as if the user had typed it, flashes its tab title, and "
            "(if the user has granted permission) shows a desktop "
            "notification. The dashboard's own LLM client then takes "
            "the conversation forward, so the user can keep typing in "
            "the browser instead of inside this MCP client. Returns the "
            "dashboard URL the user should focus and the count of "
            "currently-connected dashboard subscribers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "The text to inject as the user's turn in the "
                        "dashboard chat. Plain natural language; the "
                        "dashboard's LLM will respond."
                    ),
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    ),
]


def is_extra(name: str) -> bool:
    """Return ``True`` if ``name`` is one of CEGM's ``cegm.*`` tools."""
    return name.startswith("cegm.")


async def dispatch(
    name: str,
    arguments: dict[str, Any],
    bus: EventBus,
) -> Sequence[types.ContentBlock]:
    """Execute a CEGM extra tool. Raises :class:`KeyError` on unknown name."""
    if name == "cegm.activity_recent":
        limit = int(arguments.get("limit", 50))
        events = bus.recent(limit)
        payload = json.dumps(events, ensure_ascii=False, default=str, indent=2)
        return [types.TextContent(type="text", text=payload)]

    if name == "cegm.dashboard_chat":
        msg = arguments.get("message")
        if not isinstance(msg, str) or not msg.strip():
            raise ValueError("'message' must be a non-empty string")
        evt = Event.make("dashboard_chat_request", {"message": msg})
        await bus.publish(evt)
        payload = json.dumps(
            {
                "ok": True,
                "url": "http://127.0.0.1:27077/",
                "delivered_at": evt["ts"],
                "dashboard_subscribers": bus.subscriber_count,
                "note": (
                    "Message broadcast to all open dashboard tabs. They "
                    "will auto-submit it. The user picks up the conversation "
                    "in the browser; their next assistant turn streams "
                    "back through /api/chat there. If subscribers is 0 the "
                    "user has no dashboard open; tell them to visit the URL."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        return [types.TextContent(type="text", text=payload)]

    raise KeyError(f"unknown CEGM tool: {name!r}")
