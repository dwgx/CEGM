"""Recipe engine — guided multi-step workflows for common RE tasks.

Recipes automate the repetitive "scan → narrow → watch → freeze" loop.
Each recipe is a state machine: the LLM calls the same tool repeatedly,
passing the ``recipe_id`` from the previous call, and the recipe advances
its internal state.

The first shipping recipe is ``find_numeric_stat`` — the #1 use case:
find a health/mana/ammo/gold value in a game process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cegm_broker._logging import get_logger

_log = get_logger(__name__)


@dataclass(slots=True)
class RecipeState:
    """One active recipe instance."""

    recipe_id: str
    name: str
    vt: str
    state: str  # "scanning" | "narrowing" | "identifying" | "done"
    created_at: str
    updated_at: str
    scan_count: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    watch_ids: list[str] = field(default_factory=list)
    target_value: str = ""
    confirmed_address: str = ""
    message_to_user: str = ""

    def age_s(self) -> float:
        """Seconds since last update. Recipes expire after 10 minutes idle."""
        try:
            updated = datetime.fromisoformat(self.updated_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return 0
        return (datetime.now(UTC) - updated).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "name": self.name,
            "vt": self.vt,
            "state": self.state,
            "scan_count": self.scan_count,
            "candidate_count": len(self.candidates),
            "candidates": self.candidates,
            "watch_ids": self.watch_ids,
            "target_value": self.target_value,
            "confirmed_address": self.confirmed_address,
            "message_to_user": self.message_to_user,
        }


@dataclass(slots=True)
class RecipeRegistry:
    """In-memory recipe store. Bounded and auto-expiring."""

    _recipes: dict[str, RecipeState] = field(default_factory=dict)
    _max_recipes: int = 8
    _max_age_s: float = 600  # 10 minutes

    def _expire_old(self) -> None:
        stale = [rid for rid, r in self._recipes.items() if r.age_s() > self._max_age_s]
        for rid in stale:
            del self._recipes[rid]

    def _cap(self) -> None:
        while len(self._recipes) > self._max_recipes:
            oldest = min(self._recipes.values(), key=lambda r: r.updated_at)
            del self._recipes[oldest.recipe_id]

    def get(self, recipe_id: str) -> RecipeState | None:
        """Read a recipe without extending its lifetime."""
        r = self._recipes.get(recipe_id)
        if r is None:
            return None
        if r.age_s() > self._max_age_s:
            del self._recipes[recipe_id]
            return None
        return r

    def touch(self, recipe_id: str) -> RecipeState | None:
        """Read a recipe AND extend its lifetime (for active use)."""
        r = self.get(recipe_id)
        if r is not None:
            self._timestamp(r)
        return r

    def start(self, *, name: str, vt: str, message: str = "") -> RecipeState:
        self._expire_old()
        self._cap()
        now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        r = RecipeState(
            recipe_id=f"recipe-{uuid4()}",
            name=name,
            vt=vt,
            state="scanning",
            created_at=now,
            updated_at=now,
            message_to_user=message,
        )
        self._recipes[r.recipe_id] = r
        return r

    @staticmethod
    def _timestamp(r: RecipeState) -> None:
        r.updated_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def advance(
        self,
        recipe_id: str,
        *,
        state: str,
        scan_count: int | None = None,
        candidates: list[dict[str, Any]] | None = None,
        watch_ids: list[str] | None = None,
        target_value: str = "",
        confirmed_address: str = "",
        message_to_user: str = "",
    ) -> RecipeState | None:
        r = self.get(recipe_id)
        if r is None:
            return None
        r.state = state
        if scan_count is not None:
            r.scan_count = scan_count
        if candidates is not None:
            r.candidates = list(candidates)
        if watch_ids is not None:
            r.watch_ids = list(watch_ids)
        if target_value:
            r.target_value = target_value
        if confirmed_address:
            r.confirmed_address = confirmed_address
        if message_to_user:
            r.message_to_user = message_to_user
        self._timestamp(r)
        return r

    def remove(self, recipe_id: str) -> bool:
        return self._recipes.pop(recipe_id, None) is not None

    def list(self) -> list[RecipeState]:
        self._expire_old()
        return list(self._recipes.values())
