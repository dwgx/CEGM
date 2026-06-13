"""Address groups — named collections of watched addresses.

Groups let the AI (or user) organize discovered addresses into logical
sets: "Player Stats" (HP, MaxHP, Mana), "Weapons" (ammo, fire rate), etc.
Groups support batch freeze/unfreeze and are persisted per game profile.
"""

from __future__ import annotations

import builtins
import contextlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from cegm_broker._logging import get_logger
from cegm_broker._paths import data_root, ensure_dir

_log = get_logger(__name__)


@dataclass(slots=True)
class Group:
    group_id: str
    name: str
    addresses: list[str]  # watch_ids or raw addresses
    color: str  # hex color for UI tag
    created_at: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "addresses": self.addresses,
            "color": self.color,
            "created_at": self.created_at,
            "note": self.note,
        }


GROUP_COLORS = [
    "#3B8FD6",  # blue
    "#40A040",  # green
    "#E89333",  # amber
    "#C25B5B",  # red
    "#4EA5A5",  # teal
    "#B8A04D",  # olive
    "#6C7EC4",  # steel
    "#A060A0",  # purple
]


@dataclass(slots=True)
class GroupRegistry:
    _groups: dict[str, Group] = field(default_factory=dict)
    _color_idx: int = 0

    def _next_color(self) -> str:
        c = GROUP_COLORS[self._color_idx % len(GROUP_COLORS)]
        self._color_idx += 1
        return c

    def create(self, name: str, addresses: list[str] | None = None, note: str = "") -> Group:
        g = Group(
            group_id=f"grp-{uuid4()}",
            name=name,
            addresses=list(addresses or []),
            color=self._next_color(),
            created_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            note=note,
        )
        self._groups[g.group_id] = g
        self._auto_save()
        return g

    def add(self, group_id: str, address: str) -> Group | None:
        g = self._groups.get(group_id)
        if g and address not in g.addresses:
            g.addresses.append(address)
            self._auto_save()
        return g

    def remove_addr(self, group_id: str, address: str) -> Group | None:
        g = self._groups.get(group_id)
        if g and address in g.addresses:
            g.addresses.remove(address)
            self._auto_save()
        return g

    def delete(self, group_id: str) -> bool:
        g = self._groups.pop(group_id, None)
        if g is not None:
            self._auto_save()
            return True
        return False

    def addresses_for(self, group_id: str) -> builtins.list[str]:
        """Return the address list for a group (for unfreeze on delete)."""
        g = self._groups.get(group_id)
        return list(g.addresses) if g else []

    def get(self, group_id: str) -> Group | None:
        return self._groups.get(group_id)

    def list(self) -> builtins.list[Group]:
        return list(self._groups.values())

    def find_by_address(self, address: str) -> builtins.list[Group]:
        return [g for g in self._groups.values() if address in g.addresses]

    def _profile_path(self) -> Path:
        return data_root() / "profiles" / "groups.json"

    def save_to_disk(self) -> None:
        path = self._profile_path()
        ensure_dir(path.parent)
        payload = {gid: g.to_dict() for gid, g in self._groups.items()}
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def load_from_disk(self) -> int:
        path = self._profile_path()
        if not path.exists():
            return 0
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        if not isinstance(raw, dict):
            return 0
        loaded = 0
        for gid, d in raw.items():
            if not isinstance(d, dict):
                continue
            g = Group(
                group_id=gid,
                name=str(d.get("name", "")),
                addresses=list(d.get("addresses", [])),
                color=str(d.get("color", GROUP_COLORS[0])),
                created_at=str(d.get("created_at", "")),
                note=str(d.get("note", "")),
            )
            self._groups[gid] = g
            loaded += 1
        return loaded

    def _auto_save(self) -> None:
        with contextlib.suppress(OSError):
            self.save_to_disk()
