"""Scan-result registry for the dashboard's "Scans" panel.

Upstream (miscusi-peek) maintains a single active ``MemScan`` per CE
session. Our broker keeps a thin index on top: every time we call
``scan_all`` or ``next_scan`` via the proxy, we tag the resulting page
with a fresh ``scan_id`` and snapshot the first page of addresses so
the dashboard can show "Scan 3 — 107 hits" cards without re-querying.

Snapshots are read-only and cheap; only the **most recent** scan can
be narrowed (because that's the only one upstream still has live).

Session persistence: scans are auto-saved to disk on every record and
can be restored on broker restart.
"""

from __future__ import annotations

import contextlib
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

from cegm_broker._paths import data_root, ensure_dir

_DEFAULT_HISTORY: Final[int] = 32
_PAGE_LIMIT: Final[int] = 200


@dataclass(slots=True)
class ScanRecord:
    """One historical scan + its first page of results."""

    scan_id: str
    started_at: str
    value: str
    vt: str
    op: str
    parent_id: str | None
    count: int
    page_size: int
    results: list[dict[str, Any]]
    note: str = ""


def _session_path() -> Path:
    return data_root() / "sessions" / "scans.json"


@dataclass(slots=True)
class ScanRegistry:
    """In-memory scan history. Bounded ring buffer."""

    history: deque[ScanRecord] = field(default_factory=lambda: deque(maxlen=_DEFAULT_HISTORY))
    _auto_persist: bool = True

    def save_to_disk(self) -> None:
        """Persist scan records to disk for session restore."""
        path = _session_path()
        ensure_dir(path.parent)
        payload = [
            {
                "scan_id": r.scan_id,
                "started_at": r.started_at,
                "value": r.value,
                "vt": r.vt,
                "op": r.op,
                "parent_id": r.parent_id,
                "count": r.count,
                "page_size": r.page_size,
                "results": r.results,
                "note": r.note,
            }
            for r in self.history
        ]
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def load_from_disk(self) -> int:
        """Restore scans from disk. Returns the count of restored records."""
        path = _session_path()
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
            rec = ScanRecord(
                scan_id=entry.get("scan_id", f"scan-{uuid4()}"),
                started_at=entry.get("started_at", ""),
                value=str(entry.get("value", "")),
                vt=str(entry.get("vt", "int32")),
                op=str(entry.get("op", "exact")),
                parent_id=entry.get("parent_id"),
                count=int(entry.get("count", 0)),
                page_size=int(entry.get("page_size", 0)),
                results=list(entry.get("results", [])),
                note=str(entry.get("note", "")),
            )
            self.history.append(rec)
            loaded += 1
        return loaded

    def record(
        self,
        *,
        value: str,
        vt: str,
        op: str,
        count: int,
        results: list[dict[str, Any]],
        parent_id: str | None = None,
        note: str = "",
    ) -> ScanRecord:
        """Tag a fresh scan and stash its first page."""
        rec = ScanRecord(
            scan_id=f"scan-{uuid4()}",
            started_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            value=value,
            vt=vt,
            op=op,
            parent_id=parent_id,
            count=count,
            page_size=min(_PAGE_LIMIT, len(results)),
            results=list(results)[:_PAGE_LIMIT],
            note=note,
        )
        self.history.append(rec)
        if self._auto_persist:
            with contextlib.suppress(OSError):
                self.save_to_disk()
        return rec

    def latest(self) -> ScanRecord | None:
        return self.history[-1] if self.history else None

    def get(self, scan_id: str) -> ScanRecord | None:
        for rec in reversed(self.history):
            if rec.scan_id == scan_id:
                return rec
        return None

    def remove(self, scan_id: str) -> bool:
        """Remove a record. Returns ``True`` if it was found."""
        # Use a temporary list to filter — bounded at history maxlen so
        # this is O(n) with n ≤ 32, negligible cost.
        new = deque((r for r in self.history if r.scan_id != scan_id), maxlen=self.history.maxlen)
        found = len(new) < len(self.history)
        self.history = new
        return found

    def snapshot(self, limit: int = 16) -> list[dict[str, Any]]:
        """Return a JSON-friendly summary of recent scans, newest first."""
        out: list[dict[str, Any]] = []
        for rec in list(self.history)[-limit:][::-1]:
            out.append(
                {
                    "scan_id": rec.scan_id,
                    "started_at": rec.started_at,
                    "value": rec.value,
                    "vt": rec.vt,
                    "op": rec.op,
                    "parent_id": rec.parent_id,
                    "count": rec.count,
                    "page_size": rec.page_size,
                    "note": rec.note,
                }
            )
        return out
