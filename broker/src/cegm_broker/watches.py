"""Live "watches" — addresses the dashboard polls and renders as a grid.

Mirrors Cheat Engine's bottom-row watch panel. The user (or an LLM via
``cegm.watch_add``) marks an address; a background asyncio task reads
each watched address every ~250 ms and publishes ``watch_update``
events on the bus when a value changes (or every Nth tick if no
change, so the dashboard knows we're alive).

Freeze support: ``cegm.watch_freeze`` sets a target value that the
poller re-writes on every deviation. This is how "infinite HP" works.

Session persistence: watch definitions are debounced-saved to disk.
An address index provides O(1) dedup lookup.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

from cegm_broker._logging import get_logger
from cegm_broker._paths import data_root, ensure_dir
from cegm_broker.event_bus import Event, EventBus

_log = get_logger(__name__)

_POLL_INTERVAL_S: Final[float] = 0.25
_HEARTBEAT_TICKS: Final[int] = 8  # one heartbeat every ~2s
_DEBOUNCE_S: Final[float] = 0.6  # debounce disk writes

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

VT_WRITERS: Final[dict[str, str]] = {
    "byte": "write_integer",
    "word": "write_integer",
    "dword": "write_integer",
    "qword": "write_integer",
    "int": "write_integer",
    "int8": "write_integer",
    "int16": "write_integer",
    "int32": "write_integer",
    "int64": "write_integer",
    "uint": "write_integer",
    "uint32": "write_integer",
    "float": "write_float",
    "double": "write_double",
    "string": "write_string",
}


@dataclass(slots=True)
class Watch:
    watch_id: str
    address: str
    vt: str
    label: str
    last_value: Any = None
    last_seen_ts: str = ""
    error: str | None = None
    freeze_value: Any = None
    freeze_min: float | None = None
    freeze_max: float | None = None
    before_value: Any = None


ValueReader = Callable[[str, str], Awaitable[Any]]
ValueWriter = Callable[[str, str, Any], Awaitable[None]]


@dataclass(slots=True)
class WatchRegistry:
    bus: EventBus
    reader: ValueReader
    writer: ValueWriter | None = None
    interval_s: float = _POLL_INTERVAL_S
    _watches: dict[str, Watch] = field(default_factory=dict)
    _addr_index: dict[tuple[str, str], str] = field(default_factory=dict)
    _task: asyncio.Task[None] | None = None
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    _dirty: bool = False
    _pending_save: asyncio.Task[None] | None = None

    # ── persistence (debounced) ────────────────────────────────────────

    def _schedule_save(self) -> None:
        self._dirty = True
        if self._pending_save is None or self._pending_save.done():
            self._pending_save = asyncio.create_task(self._debounced_save())

    async def _debounced_save(self) -> None:
        await asyncio.sleep(_DEBOUNCE_S)
        if self._dirty:
            self._dirty = False
            with contextlib.suppress(OSError):
                self.save_to_disk()

    # ── CRUD ───────────────────────────────────────────────────────────

    def add(self, address: str, vt: str, label: str = "") -> Watch:
        idx_key = (address.lower(), vt)
        existing_id = self._addr_index.get(idx_key)
        if existing_id and existing_id in self._watches:
            w = self._watches[existing_id]
            if label:
                w.label = label
            self._schedule_save()
            return w
        w = Watch(watch_id=f"watch-{uuid4()}", address=address, vt=vt, label=label)
        self._watches[w.watch_id] = w
        self._addr_index[idx_key] = w.watch_id
        self._schedule_save()
        return w

    def remove(self, key: str) -> bool:
        if key in self._watches:
            w = self._watches[key]
            self._addr_index.pop((w.address.lower(), w.vt), None)
            del self._watches[key]
            self._schedule_save()
            return True
        key_lower = key.lower()
        for idx_k, wid in list(self._addr_index.items()):
            if idx_k[0] == key_lower and wid in self._watches:
                del self._watches[wid]
                self._addr_index.pop(idx_k, None)
                self._schedule_save()
                return True
        return False

    def freeze(
        self,
        key: str,
        value: Any,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> Watch | None:
        w = self._find(key)
        if w is None:
            return None
        w.freeze_value = value
        w.freeze_min = min_value
        w.freeze_max = max_value
        self._schedule_save()
        return w

    def unfreeze(self, key: str) -> Watch | None:
        w = self._find(key)
        if w is None:
            return None
        w.freeze_value = None
        self._schedule_save()
        return w

    def _find(self, key: str) -> Watch | None:
        if key in self._watches:
            return self._watches[key]
        key_lower = key.lower()
        for idx_k, wid in self._addr_index.items():
            if idx_k[0] == key_lower and wid in self._watches:
                return self._watches[wid]
        return None

    def frozen(self) -> list[Watch]:
        return [w for w in self._watches.values() if w.freeze_value is not None]

    def list(self) -> list[Watch]:
        return list(self._watches.values())

    # ── disk persistence ───────────────────────────────────────────────

    def _persist_path(self) -> Path:
        return data_root() / "sessions" / "watches.json"

    def save_to_disk(self) -> None:
        path = self._persist_path()
        ensure_dir(path.parent)
        payload = [
            {
                "watch_id": w.watch_id,
                "address": w.address,
                "vt": w.vt,
                "label": w.label,
                "freeze_value": w.freeze_value,
                "freeze_min": w.freeze_min,
                "freeze_max": w.freeze_max,
            }
            for w in self._watches.values()
        ]
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def load_from_disk(self) -> int:
        path = self._persist_path()
        if not path.exists():
            return 0
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        if not isinstance(raw, list):
            return 0
        loaded = 0
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            w = Watch(
                watch_id=entry.get("watch_id", f"watch-{uuid4()}"),
                address=str(entry.get("address", "")),
                vt=str(entry.get("vt", "int32")),
                label=str(entry.get("label", "")),
                freeze_value=entry.get("freeze_value"),
                freeze_min=entry.get("freeze_min"),
                freeze_max=entry.get("freeze_max"),
            )
            self._watches[w.watch_id] = w
            self._addr_index[(w.address.lower(), w.vt)] = w.watch_id
            loaded += 1
        return loaded

    # ── poller lifecycle ───────────────────────────────────────────────

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="cegm-watch-poller")
        _log.info("watches.poller_started", extra={"interval_s": self.interval_s})

    async def stop(self) -> None:
        self._stop_event.set()
        if self._pending_save is not None:
            self._pending_save.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pending_save
        # Force final save
        if self._dirty:
            self._dirty = False
            with contextlib.suppress(OSError):
                self.save_to_disk()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        _log.info("watches.poller_stopped")

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
                                "frozen": w.freeze_value is not None,
                            },
                        )
                    )

                # Freeze: re-write if value deviates
                if (
                    w.freeze_value is not None
                    and self.writer is not None
                    and new_value != w.freeze_value
                ):
                    try:
                        fv = float(w.freeze_value)
                    except (TypeError, ValueError):
                        fv = 0
                    if w.freeze_min is not None and fv < w.freeze_min:
                        _log.warning(
                            "watches.freeze_below_min",
                            extra={
                                "watch_id": w.watch_id,
                                "freeze_value": fv,
                                "min": w.freeze_min,
                            },
                        )
                        continue
                    if w.freeze_max is not None and fv > w.freeze_max:
                        _log.warning(
                            "watches.freeze_above_max",
                            extra={
                                "watch_id": w.watch_id,
                                "freeze_value": fv,
                                "max": w.freeze_max,
                            },
                        )
                        continue
                    w.before_value = new_value
                    try:
                        await self.writer(w.address, w.vt, w.freeze_value)
                    except Exception as exc:
                        _log.warning(
                            "watches.freeze_write_failed",
                            extra={
                                "watch_id": w.watch_id,
                                "address": w.address,
                                "err": repr(exc),
                            },
                        )

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_s)
