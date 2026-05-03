"""Live "watches" — addresses the dashboard polls and renders as a grid.

Mirrors Cheat Engine's bottom-row watch panel. The user (or an LLM via
``cegm.watch_add``) marks an address; a background asyncio task reads
each watched address every ~250 ms and publishes ``watch_update``
events on the bus when a value changes (or every Nth tick if no
change, so the dashboard knows we're alive).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final
from uuid import uuid4

from cegm_broker._logging import get_logger
from cegm_broker.event_bus import Event, EventBus

_log = get_logger(__name__)

_POLL_INTERVAL_S: Final[float] = 0.25
_HEARTBEAT_TICKS: Final[int] = 8  # one heartbeat every ~2s

# Map an MCP value-type slug to the upstream "read_*" tool that returns the
# right primitive. Kept as data so the LLM can introspect via ``vt`` errors.
VT_READERS: Final[dict[str, str]] = {
    "byte": "read_integer",
    "word": "read_integer",
    "dword": "read_integer",
    "qword": "read_integer",
    "int": "read_integer",
    "int8": "read_integer",
    "int16": "read_integer",
    "int32": "read_integer",
    "int64": "read_integer",
    "uint": "read_integer",
    "uint32": "read_integer",
    "float": "read_float",
    "double": "read_double",
    "string": "read_string",
}

VT_BYTE_LENGTH: Final[dict[str, int]] = {
    "byte": 1,
    "int8": 1,
    "word": 2,
    "int16": 2,
    "dword": 4,
    "int": 4,
    "int32": 4,
    "uint": 4,
    "uint32": 4,
    "float": 4,
    "qword": 8,
    "int64": 8,
    "double": 8,
}


@dataclass(slots=True)
class Watch:
    """One address being polled."""

    watch_id: str
    address: str
    vt: str
    label: str
    last_value: Any = None
    last_seen_ts: str = ""
    error: str | None = None


# Caller-supplied callable that reads a single ``vt``-typed value at ``address``.
# Plumbed by the broker so the registry doesn't reach back into mcp_proxy directly.
ValueReader = Callable[[str, str], Awaitable[Any]]


@dataclass(slots=True)
class WatchRegistry:
    """Set of currently-watched addresses + a background poller."""

    bus: EventBus
    reader: ValueReader
    interval_s: float = _POLL_INTERVAL_S
    _watches: dict[str, Watch] = field(default_factory=dict)
    _task: asyncio.Task[None] | None = None
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    def add(self, address: str, vt: str, label: str = "") -> Watch:
        for w in self._watches.values():
            if w.address.lower() == address.lower() and w.vt == vt:
                if label:
                    w.label = label
                return w
        w = Watch(watch_id=f"watch-{uuid4()}", address=address, vt=vt, label=label)
        self._watches[w.watch_id] = w
        return w

    def remove(self, key: str) -> bool:
        """``key`` may be a ``watch_id`` or a literal address."""
        if key in self._watches:
            del self._watches[key]
            return True
        for wid, w in list(self._watches.items()):
            if w.address.lower() == key.lower():
                del self._watches[wid]
                return True
        return False

    def list(self) -> list[Watch]:
        return list(self._watches.values())

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="cegm-watch-poller")
        _log.info("watches.poller_started", extra={"interval_s": self.interval_s})

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                _log.warning("watches.poller_error_on_stop", extra={"err": repr(exc)})
            self._task = None

    async def _run(self) -> None:
        tick = 0
        while not self._stop_event.is_set():
            tick += 1
            for w in list(self._watches.values()):
                try:
                    new_value = await self.reader(w.address, w.vt)
                except Exception as exc:
                    err = repr(exc)
                    if w.error != err:
                        w.error = err
                        await self.bus.publish(
                            Event.make(
                                "watch_update",
                                {
                                    "watch_id": w.watch_id,
                                    "address": w.address,
                                    "vt": w.vt,
                                    "label": w.label,
                                    "error": err,
                                },
                            )
                        )
                    continue
                w.error = None
                changed = new_value != w.last_value
                heartbeat = tick % _HEARTBEAT_TICKS == 0
                if changed or heartbeat:
                    w.last_value = new_value
                    w.last_seen_ts = (
                        datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                    )
                    await self.bus.publish(
                        Event.make(
                            "watch_update",
                            {
                                "watch_id": w.watch_id,
                                "address": w.address,
                                "vt": w.vt,
                                "label": w.label,
                                "value": new_value,
                                "ts": w.last_seen_ts,
                                "changed": changed,
                            },
                        )
                    )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_s)
        _log.info("watches.poller_stopped")
