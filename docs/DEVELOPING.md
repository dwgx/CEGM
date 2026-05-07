# Developing CEGM

## Quick start

```powershell
git clone --recurse-submodules https://github.com/dwgx/CEGM.git
cd CEGM\broker
uv sync --extra dev
uv run cegm-broker --dev    # hot-reload enabled
```

Open `http://127.0.0.1:27077/` — the dashboard auto-refreshes when you edit files in `web/`.

## Hot reload

When you run with `--dev`, the broker watches the `web/` directory for changes.
Any save to `.html`, `.css`, or `.js` files triggers a `broker_reload` event on
the WebSocket, and all connected browser tabs call `location.reload()`.

**Debounce:** rapid saves within 300ms are coalesced into a single reload.

**Skipped files:** dotfiles, `*.tmp`, `*.swp`, `*~`.

```powershell
# Dev mode (hot reload active)
uv run cegm-broker --dev

# Production (no file watching overhead)
uv run cegm-broker
```

## File override protection

When editing static files in `web/`:

- The broker serves files from disk via Starlette `StaticFiles`. Changes take
  effect immediately on the next HTTP request (no caching in dev).
- Hot reload ensures the browser always shows the latest version.
- **Workspace data** (watches, groups, scans) is persisted to
  `%LOCALAPPDATA%\CEGM\` and survives broker restarts. If you change the
  persistence schema, bump the version in `_paths.py`.

To force-override stale browser state:
1. Hard-refresh: `Ctrl+Shift+R`
2. Clear workspace data: delete `%LOCALAPPDATA%\CEGM\`
3. Restart broker with `--dev` for clean state

## Project layout

```
CEGM/
├── broker/                    Python package (cegm-broker on PyPI)
│   ├── pyproject.toml         Dependencies, build, tool config
│   ├── src/cegm_broker/       Broker source
│   │   ├── server.py          Starlette app factory + uvicorn launcher
│   │   ├── api.py             REST endpoints (/api/health, /api/chat, ...)
│   │   ├── mcp_server.py      MCP Server (list_tools, call_tool dispatch)
│   │   ├── mcp_proxy.py       Spawns miscusi-peek child, proxies tools
│   │   ├── mcp_extras.py      CEGM custom tools (cegm.* namespace)
│   │   ├── watches.py         Live address watches + freeze poller
│   │   ├── scans.py           Scan result registry
│   │   ├── groups.py          Address group registry
│   │   ├── recipes.py         Guided workflow state machines
│   │   ├── dynamic_tools.py   Runtime-defined custom.* tools
│   │   ├── llm.py             OpenAI-compatible LLM client
│   │   ├── event_bus.py       In-process async event fan-out
│   │   ├── config.py          Pydantic config model + JSON persistence
│   │   ├── system_prompt.py   Chat system message builder
│   │   ├── hot_reload.py      Dev file watcher
│   │   ├── parent_watch.py    CE PID monitor
│   │   ├── ws.py              WebSocket endpoint
│   │   ├── _logging.py        Structured JSONL logging
│   │   ├── _paths.py          Data/config directory resolution
│   │   └── cli.py             argparse entry point
│   └── tests/                 pytest + pytest-asyncio tests
├── web/                       Static dashboard (vanilla HTML/CSS/JS)
│   ├── index.html             Shell layout (toolbar, sidebar, panels)
│   ├── style.css              Design system (VRCSM/M3, ~320 lines)
│   └── js/                    ES2022 modules (no build step)
│       ├── main.js            Entry — wires all modules
│       ├── workspace.js       Memory editor table + inspector
│       ├── inspector.js       Right dock property panel
│       ├── console.js         Bottom console with color-coded lines
│       ├── chat.js            SSE streaming chat
│       ├── scans.js           Scan result cards
│       ├── timeline.js        Chronological event stream
│       ├── tools.js           Tool browser (filterable, categorized)
│       ├── lua.js             Lua sandbox playground
│       ├── hex.js             Memory hex viewer
│       ├── settings.js        Settings drawer
│       ├── api.js             REST helpers (fetchHealth, postChat, ...)
│       ├── ws.js              WebSocket client
│       ├── i18n.js            Tiny i18n (en/zh)
│       └── notify.js          Desktop notifications
├── plugin/                    CE Lua autorun bundle
├── vendor/                    Git submodule: miscusi-peek/cheatengine-mcp-bridge
├── docs/                      Architecture, roadmap, tool spec, ADRs
├── scripts/                   install.ps1 + dev helpers
└── examples/                  MCP client config snippets
```

## Adding a new CEGM tool

1. Add a `types.Tool(...)` entry to `EXTRAS_TOOL_DEFS` in `mcp_extras.py`
2. Add an `if name == "cegm.your_tool":` branch to `dispatch()` in the same file
3. If it needs new state, add a registry class (see `groups.py` as template)
4. Wire the registry into `server.py` lifespan and `app.state`
5. Pass it through `mcp_server.py` and `api.py` dispatch calls
6. Document in `docs/TOOL_SPEC.md`
7. Add tests in `broker/tests/`

## Adding a new Web panel

1. Create `web/js/yourpanel.js` (export a `bindYourPanel({onEvent})` function)
2. Add sidebar item + content tab + panel div in `web/index.html`
3. Import and call `bindYourPanel(...)` in `web/js/main.js`
4. Add i18n strings in `web/js/i18n.js`

## Code quality

```powershell
cd broker
uv run ruff check src/cegm_broker/     # lint
uv run ruff format src/cegm_broker/     # format
uv run mypy src/cegm_broker/            # type-check
uv run pytest                           # 50 tests, coverage ≥ 53%
```

Pre-commit: all four must pass. CI enforces this in `.github/workflows/ci.yml`.

## Key constraints

- **No build step** for the web frontend (Phase 1). Vanilla ES2022 modules.
- **No extra dependencies** beyond what's in `pyproject.toml`.
- **Localhost-only** binding (127.0.0.1). Never `0.0.0.0`.
- **GPL-2.0-only** license. Don't introduce GPL-3 or proprietary deps.
- **Thread safety**: most state lives in asyncio. Thread-safe dataclasses use
  `threading.RLock` where needed (see `dynamic_tools.py`).
