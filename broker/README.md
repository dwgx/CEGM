# broker/ — CEGM Python broker

The long-running broker. Auto-spawned by `plugin/cegm.lua` on Cheat Engine startup. Hosts an MCP Streamable HTTP server, a built-in browser dashboard, and a WebSocket event stream — all on `http://127.0.0.1:27077` by default. Spawns the vendored [miscusi-peek/cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge) Python child as a stdio MCP server and proxies its tools through.

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) and [ADR-0004](../docs/decisions/0004-build-on-miscusi-peek.md).

## Stack

- Python 3.12+
- [`mcp`](https://pypi.org/project/mcp/) 1.27+ (FastMCP merged in-tree)
- `starlette` + `uvicorn[standard]` for HTTP + WebSocket
- `openai` SDK with custom `base_url` for LLM (default DeepSeek)
- `anyio` for async, `pydantic` v2 for models, `psutil` for parent-PID watching
- `ruff` (format + lint), `mypy --strict`, `pytest` + `pytest-asyncio`
- `uv` for env management and distribution (`uv tool install cegm-broker`)

## Layout (Phase 1)

```
broker/
├── pyproject.toml           # PEP 621 metadata, all deps + dev deps, tool configs
├── .python-version          # 3.12
├── README.md
├── src/cegm_broker/
│   ├── __init__.py          # __version__
│   ├── __main__.py          # python -m cegm_broker -> cli.main()
│   ├── cli.py               # argparse: --port, --parent-pid, --log-level, --print-config
│   ├── config.py            # %LOCALAPPDATA%/CEGM/config.json loader (Pydantic)
│   ├── _logging.py          # JSONL logger to file + stderr
│   ├── server.py            # Starlette app, route mount
│   ├── mcp_proxy.py         # spawns miscusi-peek child, forwards tools/list + tools/call
│   ├── mcp_extras.py        # CEGM-namespaced @mcp.tool definitions
│   ├── llm.py               # openai SDK wrapper, tool-call routing for /api/chat
│   ├── event_bus.py         # asyncio fan-out to WebSocket subscribers
│   ├── ws.py                # WebSocket handler at /events
│   ├── api.py               # /api/chat, /api/config REST endpoints
│   ├── parent_watch.py      # exits broker when CE PID disappears
│   └── snapshots.py         # snapshot store under %LOCALAPPDATA%/CEGM/snapshots/
└── tests/
    ├── conftest.py
    ├── test_smoke.py        # imports work; CLI prints help
    ├── test_mcp_proxy.py    # spawn fake child, verify tool listing + call
    ├── test_event_bus.py
    └── test_extras_cegm.py  # cegm.preview_write/commit/cancel round-trip
```

## Run (developer)

```bash
cd broker
uv sync               # creates .venv, installs deps + dev deps
uv run cegm-broker --help
uv run cegm-broker --port 27077 --log-level debug
```

## Run (end-user, once published)

```bash
uv tool install cegm-broker     # one-time
# then CE plugin spawns it automatically; manual run is also fine:
cegm-broker --port 27077
```

## Logging

Structured JSONL to `%LOCALAPPDATA%\CEGM\logs\broker-YYYYMMDD.jsonl` and mirrored to stderr. Stdout is reserved (kept clean in case we ever support MCP stdio transport). Activity events (tool calls, chat turns) are also appended to a session-specific file at `%LOCALAPPDATA%\CEGM\activity\<session_id>.jsonl`.

## Status

Scaffold only — see [docs/ROADMAP.md](../docs/ROADMAP.md) Phase 1.
