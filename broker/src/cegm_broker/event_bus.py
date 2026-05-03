"""In-process event fan-out for the dashboard's WebSocket subscribers.

A single :class:`EventBus` instance is owned by the broker. Producers
(:mod:`cegm_broker.mcp_proxy`, :mod:`cegm_broker.llm`, the API layer) call
:meth:`EventBus.publish`; the WebSocket handler creates a per-connection
:class:`Subscription` to consume. Slow consumers do not block producers —
their queue overflows and we drop the connection.

The bus also keeps a bounded ring-buffer of recent events so the
``cegm://activity/recent`` resource can return state without polling.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Final
from uuid import uuid4

from cegm_broker._logging import get_logger

_log = get_logger(__name__)

# Per-subscriber buffer. Beyond this we treat the consumer as dead.
_SUB_QUEUE_MAX: Final[int] = 1024

# Default history window for ``recent()`` — sized so a 30-minute
# tool-heavy session still fits.
_DEFAULT_HISTORY_SIZE: Final[int] = 500

# Sentinel pushed onto a subscriber's queue when the bus wants its
# ``_iter`` consumer to exit cleanly (overflow, scope close).
_POISON: Final[object] = object()


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
        # ``Event | object`` because we also push the ``_POISON`` sentinel
        # onto this queue to wake up consumers waiting on ``queue.get()``.
        self.queue: asyncio.Queue[Event | object] = asyncio.Queue(maxsize=_SUB_QUEUE_MAX)
        self.alive: bool = True


class EventBus:
    """Single-process, asyncio-native fan-out hub with bounded history."""

    def __init__(self, history_size: int = _DEFAULT_HISTORY_SIZE) -> None:
        self._subs: set[_Subscription] = set()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._history: deque[Event] = deque(maxlen=history_size)

    async def publish(self, event: Event) -> None:
        """Append to history, then fan out to every live subscriber.

        If a subscriber's queue is full we mark it dead, drop a poison-pill
        sentinel onto its queue (so the consumer's ``await queue.get()``
        wakes up and exits cleanly), and discard it. Other subscribers
        still receive normally. History is appended unconditionally so
        :meth:`recent` reflects every event regardless of subscriber liveness.
        """
        async with self._lock:
            self._history.append(event)
            dead: list[_Subscription] = []
            for sub in self._subs:
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    sub.alive = False
                    self._poison(sub)
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
                # Wake any pending ``queue.get()`` so the iterator exits
                # cleanly even if it's blocked at the moment the consumer
                # context exits.
                self._poison(sub)

    @staticmethod
    def _poison(sub: _Subscription) -> None:
        """Best-effort sentinel push so ``_iter`` can break out of ``queue.get()``."""
        with contextlib.suppress(asyncio.QueueFull):
            sub.queue.put_nowait(_POISON)

    @staticmethod
    async def _iter(sub: _Subscription) -> AsyncIterator[Event]:
        while True:
            evt = await sub.queue.get()
            if evt is _POISON or not sub.alive:
                return
            # Narrow Event | object back to Event — only ``_POISON`` is the
            # non-Event sentinel and we returned above when we saw it.
            assert isinstance(evt, Event)
            yield evt

    @property
    def subscriber_count(self) -> int:
        """Number of live subscribers (for diagnostics / health checks)."""
        return len(self._subs)

    def recent(self, limit: int = 50) -> list[Event]:
        """Return the most recent events, oldest-first, bounded by ``limit``.

        ``limit`` is clamped to ``[1, history_size]``. Suitable for the
        ``cegm://activity/recent`` MCP resource and dashboard cold-start.
        """
        if limit <= 0:
            return []
        n = min(limit, len(self._history))
        return list(self._history)[-n:]
