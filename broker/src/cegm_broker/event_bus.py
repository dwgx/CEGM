"""In-process event fan-out for the dashboard's WebSocket subscribers.

A single :class:`EventBus` instance is owned by the broker. Producers
(:mod:`cegm_broker.mcp_proxy`, :mod:`cegm_broker.llm`, the API layer) call
:meth:`EventBus.publish`; the WebSocket handler creates a per-connection
:class:`Subscription` to consume. Slow consumers do not block producers —
their queue overflows and we drop the connection.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Final
from uuid import uuid4

from cegm_broker._logging import get_logger

_log = get_logger(__name__)

# Per-subscriber buffer. Beyond this we treat the consumer as dead.
_SUB_QUEUE_MAX: Final[int] = 1024


class Event(dict[str, Any]):
    """Lightweight wrapper to make event objects ergonomic.

    A bare dict would be sufficient at runtime, but a typed wrapper makes
    misspelled keys surface early. The shape matches
    :doc:`/docs/TOOL_SPEC.md` §"Events on the WebSocket".
    """

    @classmethod
    def make(cls, kind: str, data: dict[str, Any] | None = None) -> Event:
        """Construct a fresh event with ``ts`` and ``id`` populated."""
        return cls(
            ts=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            id=f"evt-{uuid4()}",
            kind=kind,
            data=data or {},
        )


class _Subscription:
    """One queue per active WebSocket connection."""

    __slots__ = ("alive", "queue")

    def __init__(self) -> None:
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=_SUB_QUEUE_MAX)
        self.alive: bool = True


class EventBus:
    """Single-process, asyncio-native fan-out hub."""

    def __init__(self) -> None:
        self._subs: set[_Subscription] = set()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def publish(self, event: Event) -> None:
        """Enqueue ``event`` for every live subscriber.

        If a subscriber's queue is full we mark it dead and drop the event
        for that subscriber only. Other subscribers still receive normally.
        """
        async with self._lock:
            dead: list[_Subscription] = []
            for sub in self._subs:
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    sub.alive = False
                    dead.append(sub)
                    _log.warning("event_bus.subscriber_overflow")
            for sub in dead:
                self._subs.discard(sub)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[Event]]:
        """Yield an async iterator of events scoped to a single consumer."""
        sub = _Subscription()
        async with self._lock:
            self._subs.add(sub)
        try:
            yield self._iter(sub)
        finally:
            sub.alive = False
            async with self._lock:
                self._subs.discard(sub)

    @staticmethod
    async def _iter(sub: _Subscription) -> AsyncIterator[Event]:
        while sub.alive:
            evt = await sub.queue.get()
            yield evt

    @property
    def subscriber_count(self) -> int:
        """Number of live subscribers (for diagnostics / health checks)."""
        return len(self._subs)
