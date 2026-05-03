"""MCP proxy contract tests.

We don't spawn miscusi-peek's child here — that would require Cheat Engine
to be running. The tests verify graceful failure modes and config plumbing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cegm_broker.mcp_proxy import MCPProxy, ProxyConfig


def test_proxy_config_defaults_resolve_to_vendor() -> None:
    """The default entry script points into ``vendor/cheatengine-mcp-bridge/``."""
    cfg = ProxyConfig()
    assert "cheatengine-mcp-bridge" in str(cfg.entry_script)
    assert cfg.entry_script.name == "mcp_cheatengine.py"
    assert cfg.handshake_timeout_s > 0


def test_proxy_config_from_env_honors_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``CEGM_PROXY_ENTRY`` / ``CEGM_PROXY_PYTHON`` env vars override defaults."""
    fake_entry = tmp_path / "fake_entry.py"
    monkeypatch.setenv("CEGM_PROXY_ENTRY", os.fspath(fake_entry))
    monkeypatch.setenv("CEGM_PROXY_PYTHON", "/usr/bin/python3.13")

    cfg = ProxyConfig.from_env()
    assert cfg.entry_script == fake_entry
    assert cfg.python_executable == "/usr/bin/python3.13"


@pytest.mark.asyncio
async def test_proxy_start_with_missing_entry_is_graceful(tmp_path: Path) -> None:
    """``start()`` returns cleanly when the entry script doesn't exist."""
    cfg = ProxyConfig(entry_script=tmp_path / "nope.py")
    proxy = MCPProxy(cfg)
    await proxy.start()
    assert proxy.available is False
    assert proxy.tools == []
    assert proxy.error is not None
    assert "missing" in proxy.error
    await proxy.stop()  # idempotent


@pytest.mark.asyncio
async def test_proxy_call_tool_when_unavailable_raises(tmp_path: Path) -> None:
    """``call_tool`` raises ``RuntimeError`` rather than spawning the child."""
    proxy = MCPProxy(ProxyConfig(entry_script=tmp_path / "nope.py"))
    await proxy.start()
    with pytest.raises(RuntimeError, match="not connected"):
        await proxy.call_tool("read_memory", {"address": "0x1"})
