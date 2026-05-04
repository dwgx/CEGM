"""Runtime-defined MCP tools.

The 175 upstream tools cover the static surface; this module gives an
LLM the foundation to mint **new** tools when something specialized is
useful and the existing surface doesn't quite fit. A custom tool is:

  - a ``name`` (must start with ``custom.``)
  - a one-liner ``description`` the dashboard shows the user
  - a JSON-Schema ``input_schema``
  - a Lua snippet that runs inside CE's Lua engine on each call,
    receiving the call arguments as a global ``params`` table.

Tools are persisted to ``%LOCALAPPDATA%\\CEGM\\dynamic_tools.json`` so
they survive broker restarts. Definition lives entirely in this file's
schema; the actual execution path is the proxied ``evaluate_lua`` tool
(miscusi-peek already exposes safe Lua eval inside CE).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp import types

from cegm_broker._logging import get_logger
from cegm_broker._paths import data_root, ensure_dir

_log = get_logger(__name__)

_NAMESPACE_PREFIX = "custom."


@dataclass(slots=True)
class CustomTool:
    """One user / LLM-defined tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]
    lua_body: str
    created_at: str
    updated_at: str

    def to_mcp_tool(self) -> types.Tool:
        return types.Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema or {"type": "object", "properties": {}},
        )


@dataclass(slots=True)
class DynamicToolRegistry:
    """Thread-safe in-memory + on-disk registry of custom tools."""

    storage_path: Path | None = None
    _by_name: dict[str, CustomTool] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        if self.storage_path is None:
            self.storage_path = data_root() / "dynamic_tools.json"
        self._reload_from_disk()

    # ── persistence ──────────────────────────────────────────────────

    def _reload_from_disk(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning(
                "dynamic_tools.reload_failed",
                extra={"path": str(self.storage_path), "err": repr(exc)},
            )
            return
        if not isinstance(raw, dict):
            return
        with self._lock:
            self._by_name.clear()
            for name, payload in raw.items():
                if not isinstance(payload, dict):
                    continue
                try:
                    self._by_name[name] = CustomTool(
                        name=name,
                        description=str(payload.get("description", "")),
                        input_schema=dict(payload.get("input_schema", {})),
                        lua_body=str(payload.get("lua_body", "")),
                        created_at=str(payload.get("created_at", "")),
                        updated_at=str(payload.get("updated_at", "")),
                    )
                except (TypeError, ValueError) as exc:
                    _log.warning(
                        "dynamic_tools.skip_bad_record",
                        extra={"name": name, "err": repr(exc)},
                    )

    def _flush_to_disk(self) -> None:
        if self.storage_path is None:
            return
        ensure_dir(self.storage_path.parent)
        tmp = self.storage_path.with_suffix(".json.tmp")
        with self._lock:
            payload = {n: asdict(t) for n, t in self._by_name.items()}
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        tmp.replace(self.storage_path)

    # ── public API ───────────────────────────────────────────────────

    def define(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any] | None,
        lua_body: str,
    ) -> CustomTool:
        """Register a new tool or replace an existing one with the same name.

        Raises :class:`ValueError` if ``name`` doesn't start with
        ``custom.`` (so dynamic tools can never accidentally shadow an
        upstream or built-in CEGM tool).
        """
        if not isinstance(name, str) or not name.startswith(_NAMESPACE_PREFIX):
            raise ValueError(f"name must start with {_NAMESPACE_PREFIX!r}; got {name!r}")
        if not isinstance(lua_body, str) or not lua_body.strip():
            raise ValueError("lua_body must be a non-empty string")
        now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._lock:
            existing = self._by_name.get(name)
            tool = CustomTool(
                name=name,
                description=description or "(no description)",
                input_schema=dict(input_schema or {"type": "object", "properties": {}}),
                lua_body=lua_body,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            self._by_name[name] = tool
        self._flush_to_disk()
        return tool

    def undefine(self, name: str) -> bool:
        with self._lock:
            removed = self._by_name.pop(name, None) is not None
        if removed:
            self._flush_to_disk()
        return removed

    def get(self, name: str) -> CustomTool | None:
        with self._lock:
            return self._by_name.get(name)

    def all(self) -> list[CustomTool]:
        with self._lock:
            return list(self._by_name.values())

    def mcp_tools(self) -> Iterable[types.Tool]:
        for t in self.all():
            yield t.to_mcp_tool()

    @staticmethod
    def is_dynamic_name(name: str) -> bool:
        return name.startswith(_NAMESPACE_PREFIX)

    @staticmethod
    def render_invocation(tool: CustomTool, arguments: dict[str, Any]) -> str:
        """Wrap the Lua body so it sees a global ``params`` table.

        Renders the arguments as a Lua-source table literal rather than
        JSON: avoids parsing JSON inside CE's Lua engine and sidesteps
        the named-pipe bridge's quirks with multi-line ``[==[...]==]``
        long-brackets that triggered upstream JSON-RPC parse errors.
        """
        rendered = _render_lua_value(arguments or {})
        return f"local params = {rendered}\n-- ── user-supplied body ──\n{tool.lua_body}\n"


def _render_lua_value(value: Any) -> str:  # noqa: PLR0911 — type-by-type fan-out
    """Serialize a Python value as a Lua-source literal."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        # Use single-quoted Lua string with escapes for the few characters
        # that don't survive a single-quoted literal.
        escaped = (
            value.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
        return f"'{escaped}'"
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            key = str(k)
            # Use ["key"] notation to be safe with non-identifier keys.
            parts.append(f"[{_render_lua_value(key)}] = {_render_lua_value(v)}")
        return "{" + ", ".join(parts) + "}"
    if isinstance(value, list | tuple):
        return "{" + ", ".join(_render_lua_value(v) for v in value) + "}"
    return _render_lua_value(str(value))
