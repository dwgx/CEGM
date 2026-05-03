"""Scan-result registry for the dashboard's "Scans" panel.

Upstream (miscusi-peek) maintains a single active ``MemScan`` per CE
session. Our broker keeps a thin index on top: every time we call
``scan_all`` or ``next_scan`` via the proxy, we tag the resulting page
with a fresh ``scan_id`` and snapshot the first page of addresses so
the dashboard can show "Scan 3 — 107 hits" cards without re-querying.

Snapshots are read-only and cheap; only the **most recent** scan can
be narrowed (because that's the only one upstream still has live).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final
from uuid import uuid4

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


@dataclass(slots=True)
class ScanRegistry:
    """In-memory scan history. Bounded ring buffer."""

    history: deque[ScanRecord] = field(default_factory=lambda: deque(maxlen=_DEFAULT_HISTORY))

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
        for i, rec in enumerate(self.history):
            if rec.scan_id == scan_id:
                # ``deque`` doesn't support ``del[i]``; rebuild it.
                kept = [r for j, r in enumerate(self.history) if j != i]
                self.history.clear()
                self.history.extend(kept)
                return True
        return False

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
