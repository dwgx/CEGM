# broker/ — Python MCP server + LLM client + CE bridge

The long-running broker. Hosts an MCP Streamable HTTP server so external LLM clients can drive CE; embeds an OpenAI-compatible client for the in-CE chat panel; bridges to the CE Lua plugin via JSONL files under `%LOCALAPPDATA%\CEGM\rpc\` (see [ADR-0003](../docs/decisions/0003-ipc-mechanism.md)).

## Layout (planned, Phase 1)

```
broker/
├── pyproject.toml        # uv / pip metadata; entry-point cegm-broker
├── src/cegm_broker/
│   ├── __init__.py
│   ├── __main__.py       # `python -m cegm_broker` -> main()
│   ├── server.py         # FastMCP server, tool registrations
│   ├── tools.py          # @mcp.tool implementations (delegate to ce_bridge)
│   ├── resources.py      # @mcp.resource (scan results, module map)
│   ├── prompts.py        # @mcp.prompt (find-stat, follow-pointer, etc.)
│   ├── ce_bridge.py      # JSONL file IPC: append requests.jsonl, tail responses.jsonl (watchdog)
│   ├── llm.py            # OpenAI-compatible client for in-CE chat
│   ├── log.py            # structured JSONL logger; writes broker.jsonl
│   ├── config.py         # %LOCALAPPDATA%/CEGM/config.json loader
│   └── cli.py            # argparse / typer entry point
├── tests/
│   ├── test_tools.py
│   ├── test_bridge_protocol.py
│   └── fixtures/
└── README.md
```

## Run (developer, until Phase 5 installer)

```bash
# from broker/
uv venv
uv pip install -e .[dev]
uv run cegm-broker --help
uv run cegm-broker --port 27077 --log-dir %LOCALAPPDATA%/CEGM/logs
```

## Run as MCP server (end-user)

Once published to PyPI:

```bash
uv tool install cegm-broker
cegm-broker --port 27077    # leave running in a terminal, or as a service
```

External MCP clients connect to `http://127.0.0.1:27077/mcp`. See `examples/` for client configs.

## Logging

All tool calls are logged as JSON Lines to `%LOCALAPPDATA%\CEGM\rpc\events.jsonl` — the same file the CE plugin tails for the activity feed. Stderr also receives the same lines for terminal visibility. Stdout is reserved (kept clean in case we ever support MCP stdio transport).

## Status

Skeleton only — no Python files yet. See [docs/ROADMAP.md](../docs/ROADMAP.md) Phase 1.
