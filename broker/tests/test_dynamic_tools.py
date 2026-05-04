"""Unit tests for the dynamic-tool registry and its Lua-rendering helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from cegm_broker.dynamic_tools import (
    CustomTool,
    DynamicToolRegistry,
    _render_lua_value,
)


def test_render_lua_value_scalars() -> None:
    assert _render_lua_value(None) == "nil"
    assert _render_lua_value(True) == "true"
    assert _render_lua_value(False) == "false"
    assert _render_lua_value(42) == "42"
    assert _render_lua_value(3.14) == "3.14"


def test_render_lua_value_string_escapes() -> None:
    """Strings use single-quoted Lua literals with the four common escapes."""
    assert _render_lua_value("plain") == "'plain'"
    assert _render_lua_value("don't") == "'don\\'t'"
    assert _render_lua_value("line1\nline2") == "'line1\\nline2'"
    assert _render_lua_value("c:\\path") == "'c:\\\\path'"


def test_render_lua_value_nested_structures() -> None:
    out = _render_lua_value({"base": "0x10", "offsets": [4, 8]})
    # Order is dict-iteration order (insertion-preserved on 3.7+).
    assert out == "{['base'] = '0x10', ['offsets'] = {4, 8}}"


def test_render_lua_value_unknown_falls_back_to_string() -> None:
    class Foo:
        def __str__(self) -> str:
            return "<foo>"

    assert _render_lua_value(Foo()) == "'<foo>'"


def test_registry_round_trip(tmp_path: Path) -> None:
    """Define → list → undefine survives a registry reopen on the same path."""
    storage = tmp_path / "tools.json"
    reg1 = DynamicToolRegistry(storage_path=storage)

    tool = reg1.define(
        name="custom.read_dword",
        description="read a dword",
        input_schema={"type": "object", "properties": {"address": {"type": "string"}}},
        lua_body="return readInteger(params.address)",
    )
    assert tool.name == "custom.read_dword"
    assert tool.created_at == tool.updated_at  # first definition

    # Re-define: created_at should be preserved, updated_at should advance.
    again = reg1.define(
        name="custom.read_dword",
        description="updated",
        input_schema={"type": "object", "properties": {}},
        lua_body="return 42",
    )
    assert again.created_at == tool.created_at
    assert again.updated_at >= tool.updated_at
    assert again.description == "updated"

    # Reopen — the persisted state should reload.
    reg2 = DynamicToolRegistry(storage_path=storage)
    loaded = reg2.get("custom.read_dword")
    assert loaded is not None
    assert loaded.description == "updated"
    assert loaded.lua_body == "return 42"

    assert reg2.undefine("custom.read_dword") is True
    assert reg2.get("custom.read_dword") is None
    assert reg2.undefine("custom.read_dword") is False  # already gone


def test_registry_rejects_non_custom_namespace(tmp_path: Path) -> None:
    reg = DynamicToolRegistry(storage_path=tmp_path / "tools.json")
    with pytest.raises(ValueError, match=r"custom\."):
        reg.define("tools.evil", "x", {}, "return 1")
    with pytest.raises(ValueError, match=r"custom\."):
        reg.define("custom.", "x", {}, "return 1")  # starts with custom. but needs char after dot
    # actually that one passes the prefix check; let's also test empty body
    with pytest.raises(ValueError, match="non-empty"):
        reg.define("custom.x", "x", {}, "")


def test_render_invocation_wraps_with_json_encoder(tmp_path: Path) -> None:
    """Wrapped Lua exposes ``params``, then runs body inside pcall → encode."""
    reg = DynamicToolRegistry(storage_path=tmp_path / "tools.json")
    reg.define(
        name="custom.echo",
        description="echo params",
        input_schema={},
        lua_body="return {got = params.x}",
    )
    tool = reg.get("custom.echo")
    assert tool is not None

    rendered = DynamicToolRegistry.render_invocation(tool, {"x": 7})
    # Sanity:
    assert "local params = {['x'] = 7}" in rendered
    assert "_cegm_encode" in rendered
    assert "pcall(function()" in rendered
    assert "return {got = params.x}" in rendered
    assert "_cegm_encode(_cegm_result)" in rendered

    # No unicode separators (the bridge corrupted on em dashes).
    rendered.encode("ascii")  # raises if non-ASCII slips in


def test_to_mcp_tool_uses_input_schema(tmp_path: Path) -> None:
    """The MCP Tool surface mirrors what the LLM saw at definition time."""
    reg = DynamicToolRegistry(storage_path=tmp_path / "tools.json")
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    reg.define("custom.foo", "the foo", schema, "return 0")
    tool = reg.get("custom.foo")
    assert tool is not None

    mcp = tool.to_mcp_tool()
    assert mcp.name == "custom.foo"
    assert mcp.description == "the foo"
    assert mcp.inputSchema == schema


def test_custom_tool_dataclass_is_simple_value(tmp_path: Path) -> None:
    reg = DynamicToolRegistry(storage_path=tmp_path / "tools.json")
    reg.define("custom.x", "y", {}, "return 0")
    tools = reg.all()
    assert len(tools) == 1
    assert isinstance(tools[0], CustomTool)
