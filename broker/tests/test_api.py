"""HTTP endpoint tests via Starlette's TestClient (lifespan-aware)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from cegm_broker.server import build_app


def _stream_factory(
    events: list[dict[str, Any]],
) -> Callable[..., AsyncIterator[dict[str, Any]]]:
    """Build an ``astream_chat`` replacement that yields ``events`` then [DONE]."""

    async def _stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        for evt in events:
            yield evt

    return _stream


def _parse_sse(body: str) -> list[dict[str, Any] | str]:
    """Decode an SSE response body into a list of events (or the [DONE] sentinel)."""
    out: list[dict[str, Any] | str] = []
    for frame in body.split("\n\n"):
        for line in frame.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                out.append("[DONE]")
            else:
                out.append(json.loads(payload))
    return out


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


def test_chat_streams_sse_events(client: TestClient) -> None:
    """End-to-end chat: stream tokens land as SSE frames terminated by [DONE]."""
    client.put("/api/config", json={"llm": {"api_key": "sk-test"}})

    events = [
        {"type": "token", "text": "hello"},
        {"type": "token", "text": " back"},
        {"type": "done", "content": "hello back"},
    ]
    with patch("cegm_broker.api.LLMClient") as mock_llm:
        instance = mock_llm.return_value
        instance.astream_chat = _stream_factory(events)

        r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")

        decoded = _parse_sse(r.text)
        assert decoded[-1] == "[DONE]"
        token_texts = [
            e["text"] for e in decoded if isinstance(e, dict) and e.get("type") == "token"
        ]
        assert token_texts == ["hello", " back"]


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
    client.put("/api/config", json={"llm": {"api_key": "sk-test"}})
    with patch("cegm_broker.api.LLMClient") as mock_llm:
        instance = mock_llm.return_value
        instance.astream_chat = _stream_factory(
            [
                {"type": "token", "text": "ok"},
                {"type": "done", "content": "ok"},
            ]
        )
        client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "ping"}]},
        )

    with client.websocket_connect("/events") as ws:
        first = ws.receive_json()
        assert "kind" in first
        assert first["ts"].endswith("Z")
