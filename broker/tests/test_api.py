"""HTTP endpoint tests via Starlette's TestClient (lifespan-aware)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from cegm_broker.server import build_app


@pytest.fixture
def client(
    isolated_data_dir: Path,
    disabled_proxy: None,
) -> Generator[TestClient, None, None]:
    """A TestClient with a fully-initialized lifespan and stubbed proxy.

    ``isolated_data_dir`` redirects config persistence to a temp path;
    ``disabled_proxy`` sets the MCP entry to a non-existent file so the
    proxy fails-fast and doesn't try to launch miscusi-peek's child.
    """
    app = build_app()
    with TestClient(app) as c:
        yield c


def test_health_reports_proxy_unavailable(client: TestClient) -> None:
    """With CEGM_PROXY_ENTRY pointed at a missing file, proxy is unavailable."""
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["port"] > 0
    assert data["proxy"]["available"] is False
    assert data["proxy"]["tool_count"] == 0


def test_config_get_returns_sanitized(client: TestClient) -> None:
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "llm" in data
    # Empty key with no save() yet — sanitized as empty string.
    assert data["llm"]["api_key"] == ""


def test_config_put_merges_and_persists(client: TestClient) -> None:
    """PUT /api/config updates LLM settings and persists across reads."""
    payload = {
        "llm": {
            "api_key": "sk-test-12345",
            "model": "deepseek-coder",
        },
        "safety": {"preview_writes_default": True},
    }
    r = client.put("/api/config", json=payload)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["llm"]["model"] == "deepseek-coder"
    assert out["llm"]["api_key"] == "***"
    assert out["safety"]["preview_writes_default"] is True

    # Read back: should see the masked key still set.
    r2 = client.get("/api/config")
    assert r2.json()["llm"]["api_key"] == "***"


def test_config_put_blank_key_preserves_existing(client: TestClient) -> None:
    """Submitting an empty api_key should not erase the saved one."""
    client.put("/api/config", json={"llm": {"api_key": "sk-keep-me"}})
    r = client.put("/api/config", json={"llm": {"api_key": "", "model": "deepseek-chat"}})
    assert r.status_code == 200
    assert r.json()["llm"]["api_key"] == "***"  # still set, just masked


def test_chat_without_api_key_returns_400(client: TestClient) -> None:
    """Chat refuses with a clear error when no key is configured."""
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400
    assert "api_key" in r.json()["error"]


def test_chat_with_mocked_llm_round_trips(client: TestClient) -> None:
    """End-to-end chat with a fake LLM: user → assistant text returned."""
    client.put("/api/config", json={"llm": {"api_key": "sk-test"}})

    fake_response: dict[str, Any] = {"role": "assistant", "content": "hello back"}

    with patch("cegm_broker.api.LLMClient") as mock_llm:
        instance = mock_llm.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 200
        assert r.json() == fake_response
        # Sanity: the LLM was actually called once.
        instance.chat.assert_awaited_once()


def test_invalid_chat_body_returns_400(client: TestClient) -> None:
    r = client.post("/api/chat", json={"messages": "not a list"})
    assert r.status_code == 400


def test_invalid_config_body_returns_400(client: TestClient) -> None:
    r = client.put("/api/config", json={"server": {"port": -1}})
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "invalid config"
    assert "details" in body


def test_websocket_replays_recent_events(client: TestClient) -> None:
    """Connecting to /events should immediately replay any history present."""
    # Trigger a chat-user event to populate history.
    client.put("/api/config", json={"llm": {"api_key": "sk-test"}})
    with patch("cegm_broker.api.LLMClient") as mock_llm:
        instance = mock_llm.return_value
        instance.chat = AsyncMock(return_value={"role": "assistant", "content": "ok"})
        client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "ping"}]},
        )

    with client.websocket_connect("/events") as ws:
        # Expect at least one historical event on connect.
        first = ws.receive_json()
        assert "kind" in first
        assert first["ts"].endswith("Z")
