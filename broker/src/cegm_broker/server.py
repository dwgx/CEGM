"""Starlette application factory and uvicorn launcher.

Entry point for the broker's HTTP layer. The CLI calls :func:`run`; tests
call :func:`build_app` to obtain the ASGI app for ``httpx.ASGITransport``.

Routes:

- ``GET  /``                    static dashboard (``web/index.html``)
- ``GET  /api/health``          liveness probe; broker version + proxy state
- ``GET  /api/config``          sanitized config (no secrets)
- ``PUT  /api/config``          merge-patch config; persists to disk
- ``POST /api/chat``            single-shot chat completion with tool routing
- ``WS   /events``              live event stream for the dashboard
- ``ANY  /mcp``                 Streamable HTTP MCP endpoint (proxy + extras)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from cegm_broker import __version__, parent_watch
from cegm_broker._logging import get_logger
from cegm_broker.api import chat, config_get, config_put, health
from cegm_broker.config import Config
from cegm_broker.dynamic_tools import DynamicToolRegistry
from cegm_broker.event_bus import Event, EventBus
from cegm_broker.mcp_proxy import MCPProxy, ProxyConfig
from cegm_broker.mcp_server import build_server
from cegm_broker.scans import ScanRegistry
from cegm_broker.watches import WatchRegistry
from cegm_broker.ws import events_endpoint

if TYPE_CHECKING:
    from starlette.types import ASGIApp

_log = get_logger(__name__)

# Resolve the repo's web/ directory at import time. Layout:
#   <repo>/broker/src/cegm_broker/server.py
#   <repo>/web/index.html
_WEB_DIR: Path = Path(__file__).resolve().parents[3] / "web"


def _make_lifespan(parent_pid: int | None):  # type: ignore[no-untyped-def]  # noqa: PLR0915
    """Build a lifespan context manager bound to a particular ``parent_pid``."""

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:  # noqa: PLR0915
        config = Config.load()
        bus = EventBus()
        proxy = MCPProxy(ProxyConfig.from_env())
        await proxy.start()  # graceful failure if upstream isn't reachable

        scans = ScanRegistry()
        dynamic = DynamicToolRegistry()

        async def _read_value(address: str, vt: str) -> object:
            """Bridge the watch poller into the MCP proxy's read_memory family."""
            if not proxy.available:
                raise RuntimeError("proxy unavailable")
            if vt == "float":
                tool = "read_float"
            elif vt == "double":
                tool = "read_double"
            elif vt == "string":
                tool = "read_string"
            else:
                tool = "read_integer"
            res = await proxy.call_tool(tool, {"address": address})
            for block in res.content:
                text = getattr(block, "text", None)
                if text:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
            return None

        watches = WatchRegistry(bus=bus, reader=_read_value)
        watches.start()

        await bus.publish(
            Event.make(
                "broker_status",
                {
                    "version": __version__,
                    "port": config.server.port,
                    "proxy_available": proxy.available,
                    "proxy_tool_count": len(proxy.tools),
                    "proxy_error": proxy.error,
                    "custom_tool_count": len(dynamic.all()),
                },
            )
        )

        mcp_server = build_server(proxy, bus, scans=scans, watches=watches, dynamic=dynamic)
        session_mgr = StreamableHTTPSessionManager(
            mcp_server,
            json_response=True,
            stateless=True,
        )

        watcher_task: asyncio.Task[None] | None = None
        async with session_mgr.run():
            app.state.config = config
            app.state.bus = bus
            app.state.proxy = proxy
            app.state.scans = scans
            app.state.watches = watches
            app.state.dynamic = dynamic
            app.state.mcp_session_mgr = session_mgr

            if parent_pid is not None:
                watcher_task = asyncio.create_task(parent_watch.watch(parent_pid))

            _log.info(
                "broker.lifespan_started",
                extra={
                    "version": __version__,
                    "port": config.server.port,
                    "proxy_available": proxy.available,
                    "custom_tool_count": len(dynamic.all()),
                },
            )
            try:
                yield
            finally:
                if watcher_task is not None:
                    watcher_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await watcher_task
                await watches.stop()
                await proxy.stop()
                _log.info("broker.lifespan_stopped")

    return lifespan


class _MCPRouteApp:
    """ASGI app wrapper for ``/mcp`` — looks up the session manager at request time.

    Starlette's :class:`~starlette.routing.Route` distinguishes "endpoint
    function takes a ``Request``" from "endpoint is an ASGI app" by class
    shape. A plain ``async def`` is treated as the former and rejected for
    non-GET/HEAD; a class with ``__call__(scope, receive, send)`` is
    treated correctly as ASGI. This wrapper is the same shape FastMCP's
    own ``StreamableHTTPASGIApp`` uses.

    The session manager is built inside the lifespan, so we resolve it
    from ``scope["app"].state`` per-request rather than at construction.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = scope.get("app")
        session_mgr = getattr(getattr(app, "state", None), "mcp_session_mgr", None)
        if session_mgr is None:
            if scope["type"] != "http":
                return
            await send({"type": "http.response.start", "status": 503, "headers": []})
            await send({"type": "http.response.body", "body": b"MCP session manager not ready"})
            return
        await session_mgr.handle_request(scope, receive, send)


def build_app(parent_pid: int | None = None) -> ASGIApp:
    """Construct the Starlette ASGI application without binding a port."""
    routes: list[Route | WebSocketRoute | Mount] = [
        Route("/api/health", health, methods=["GET"]),
        Route("/api/config", config_get, methods=["GET"]),
        Route("/api/config", config_put, methods=["PUT"]),
        Route("/api/chat", chat, methods=["POST"]),
        WebSocketRoute("/events", events_endpoint),
        # Use Route(endpoint=<asgi-app>) — same pattern FastMCP uses internally —
        # so all HTTP methods reach the session manager. Mount("/mcp") would
        # strip the path and Starlette would 405 on POST.
        Route("/mcp", endpoint=_MCPRouteApp()),
    ]

    if _WEB_DIR.is_dir():
        # Static dashboard at "/" — mounted last so explicit routes take priority.
        routes.append(Mount("/", app=StaticFiles(directory=_WEB_DIR, html=True), name="web"))
    else:  # pragma: no cover — only hit if web/ is missing in a packaged sdist
        _log.warning("server.web_dir_missing", extra={"path": str(_WEB_DIR)})

    return Starlette(routes=routes, lifespan=_make_lifespan(parent_pid))


def run(*, host: str, port: int, parent_pid: int | None = None) -> None:
    """Block on a uvicorn server bound to ``host:port``."""
    config = uvicorn.Config(
        app=build_app(parent_pid=parent_pid),
        host=host,
        port=port,
        log_config=None,  # we own logging via _logging.py
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    server.run()
