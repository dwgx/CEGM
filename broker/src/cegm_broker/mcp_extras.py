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
from cegm_broker.event_bus import EventBus

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
    raise KeyError(f"unknown CEGM tool: {name!r}")
