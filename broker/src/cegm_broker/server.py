"""Starlette application factory and uvicorn launcher.

Entry point for the broker's HTTP layer. The CLI calls :func:`run`; tests
call :func:`build_app` to obtain the ASGI app for ``httpx.ASGITransport``.

Routes (Phase 1 layout — handlers stubbed until they land):

- ``GET  /``                    — static dashboard (``web/index.html``)
- ``GET  /api/health``          — liveness probe; returns broker version
- ``GET  /api/config``          — sanitized config (no secrets)
- ``PUT  /api/config``          — update config; reloads LLM client in place
- ``POST /api/chat``            — dashboard chat (SSE streaming response)
- ``GET  /events``              — WebSocket event stream
- ``ANY  /mcp``                 — Streamable HTTP MCP endpoint (FastMCP)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from cegm_broker import __version__
from cegm_broker._logging import get_logger
from cegm_broker.config import Config
from cegm_broker.event_bus import EventBus

if TYPE_CHECKING:
    from starlette.types import ASGIApp

_log = get_logger(__name__)

# Resolve the repo's web/ directory at import time. Layout:
#   <repo>/broker/src/cegm_broker/server.py
#   <repo>/web/index.html
_WEB_DIR: Path = Path(__file__).resolve().parents[3] / "web"


@asynccontextmanager
async def _lifespan(app: Starlette) -> AsyncIterator[None]:
    """Start and stop background services bound to app lifetime."""
    config = Config.load()
    bus = EventBus()
    app.state.config = config
    app.state.bus = bus
    _log.info(
        "broker.lifespan_started",
        extra={"version": __version__, "port": config.server.port},
    )
    try:
        # Phase 1 wires real subsystems here:
        #   - mcp_proxy.spawn(config) for the miscusi-peek child
        #   - mcp_extras.register(...) on the FastMCP server
        #   - parent_watch.watch(parent_pid) as a task
        yield
    finally:
        _log.info("broker.lifespan_stopped")


async def _health(request: Request) -> JSONResponse:
    """Liveness probe used by both humans and the CE-side port-readiness loop."""
    config: Config = request.app.state.config
    bus: EventBus = request.app.state.bus
    return JSONResponse(
        {
            "ok": True,
            "version": __version__,
            "port": config.server.port,
            "subscribers": bus.subscriber_count,
        }
    )


async def _config_get(request: Request) -> JSONResponse:
    """Return the sanitized config (no secrets)."""
    config: Config = request.app.state.config
    return JSONResponse(config.sanitized())


def build_app() -> ASGIApp:
    """Construct the Starlette ASGI application without binding a port."""
    routes: list[Route] = [
        Route("/api/health", _health, methods=["GET"]),
        Route("/api/config", _config_get, methods=["GET"]),
        # /api/config PUT, /api/chat, /events, /mcp wired in Phase 1 patches.
    ]

    app = Starlette(routes=routes, lifespan=_lifespan)

    # Static dashboard at "/". Mounted last so explicit routes take priority.
    if _WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
    else:  # pragma: no cover — only hit if web/ is missing in a packaged sdist
        _log.warning("server.web_dir_missing", extra={"path": str(_WEB_DIR)})

    return app


def run(*, host: str, port: int, parent_pid: int | None = None) -> None:
    """Block on a uvicorn server bound to ``host:port``.

    ``parent_pid`` is wired up to :mod:`cegm_broker.parent_watch` once that
    integration lands. The argument is accepted now so the CLI signature is
    stable across phases.
    """
    del parent_pid  # Phase 1 hookup pending.

    config = uvicorn.Config(
        app=build_app(),
        host=host,
        port=port,
        log_config=None,  # we own logging via _logging.py
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    server.run()
