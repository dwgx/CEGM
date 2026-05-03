"""REST endpoints for the dashboard.

- ``GET  /api/health`` — liveness probe used by the CE plugin's port test
  and by the dashboard at load.
- ``GET  /api/config`` — sanitized config snapshot (no secrets).
- ``PUT  /api/config`` — merge-patch the runtime config; persists to disk.
- ``POST /api/chat``   — dashboard chat. Phase 1 returns a single JSON body
  (non-streaming); SSE streaming lands in a Phase 1 follow-up.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from cegm_broker import __version__
from cegm_broker._logging import get_logger
from cegm_broker.config import Config
from cegm_broker.event_bus import Event, EventBus
from cegm_broker.llm import LLMClient
from cegm_broker.mcp_extras import EXTRAS_TOOL_DEFS, is_extra
from cegm_broker.mcp_extras import dispatch as dispatch_extra
from cegm_broker.mcp_proxy import MCPProxy

_log = get_logger(__name__)


async def health(request: Request) -> JSONResponse:
    """Liveness probe; also reports proxy and bus status."""
    config: Config = request.app.state.config
    bus: EventBus = request.app.state.bus
    proxy: MCPProxy = request.app.state.proxy
    return JSONResponse(
        {
            "ok": True,
            "version": __version__,
            "port": config.server.port,
            "subscribers": bus.subscriber_count,
            "proxy": {
                "available": proxy.available,
                "tool_count": len(proxy.tools),
                "error": proxy.error,
            },
        }
    )


async def config_get(request: Request) -> JSONResponse:
    """Return the sanitized config (no secrets)."""
    config: Config = request.app.state.config
    return JSONResponse(config.sanitized())


async def config_put(request: Request) -> JSONResponse:
    """Merge-patch the runtime config and persist to disk.

    The caller may send any prefix of the schema; missing fields keep
    their existing values. Empty-string ``api_key`` is treated as
    "leave unchanged" so the masked-key UX in the dashboard works.
    """
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)

    current: Config = request.app.state.config
    merged: dict[str, Any] = current.model_dump(mode="python")
    # Don't lose the SecretStr wrapper through plain dict merging.
    if isinstance(merged.get("llm"), dict):
        merged["llm"]["api_key"] = current.llm.api_key.get_secret_value()

    _deep_merge(merged, cast(dict[str, Any], body))

    # If the caller blanked api_key, preserve the existing one (dashboard
    # convention: empty input = unchanged).
    if isinstance(merged.get("llm"), dict) and merged["llm"].get("api_key") == "":
        merged["llm"]["api_key"] = current.llm.api_key.get_secret_value()

    try:
        new_config = Config.model_validate(merged)
    except ValidationError as exc:
        return JSONResponse({"error": "invalid config", "details": exc.errors()}, status_code=400)

    new_config.save()
    request.app.state.config = new_config
    _log.info("api.config_updated")
    return JSONResponse(new_config.sanitized())


async def chat(request: Request) -> JSONResponse:
    """Single-shot chat completion with full tool-call routing.

    Body schema: ``{"messages": [{"role": "user|system|...", "content": "..."}]}``.
    Returns the final assistant message after any tool round-trips.
    """
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    messages_raw = body.get("messages")
    if not isinstance(messages_raw, list):
        return JSONResponse({"error": "messages must be a list"}, status_code=400)

    config: Config = request.app.state.config
    proxy: MCPProxy = request.app.state.proxy
    bus: EventBus = request.app.state.bus

    if not config.llm.api_key.get_secret_value():
        return JSONResponse(
            {"error": "no LLM api_key configured; open Settings and save one"},
            status_code=400,
        )

    tools = [*proxy.tools, *EXTRAS_TOOL_DEFS]

    async def dispatcher(name: str, args: dict[str, Any]) -> list[Any]:
        await bus.publish(Event.make("tool_called", {"name": name, "arguments": args}))
        try:
            if is_extra(name):
                content = await dispatch_extra(name, args, bus)
            else:
                if not proxy.available:
                    raise RuntimeError(f"upstream MCP not connected; cannot dispatch {name!r}")
                upstream = await proxy.call_tool(name, args)
                content = list(upstream.content)
        except Exception as exc:
            await bus.publish(Event.make("tool_error", {"name": name, "error": repr(exc)}))
            raise
        await bus.publish(Event.make("tool_result", {"name": name, "ok": True}))
        return list(content)

    # Mirror the user message into the activity feed for visibility.
    if messages_raw and isinstance(messages_raw[-1], dict):
        last = messages_raw[-1]
        if last.get("role") == "user":
            await bus.publish(Event.make("chat_user", {"content": last.get("content")}))

    llm = LLMClient(config.llm)
    final = await llm.chat(list(messages_raw), tools, dispatcher)
    await bus.publish(Event.make("chat_assistant", {"content": final.get("content")}))
    return JSONResponse(final)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> None:
    """In-place recursive merge of ``patch`` into ``base``.

    Lists and scalars in ``patch`` overwrite ``base``; nested dicts merge.
    """
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
