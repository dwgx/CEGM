# ADR-0002: Implement the broker in Python

- **Status:** accepted
- **Date:** 2026-05-03
- **Deciders:** dwgx (project owner)

## Context

The broker is the long-running process that sits between Cheat Engine and the LLM. Its responsibilities:

- Host an MCP Streamable HTTP server so external clients (Claude Desktop, Cursor, Claude Code) can use CE as a tool
- Embed an OpenAI-compatible LLM client for the in-CE chat panel (Phase 3)
- Bridge local socket traffic to/from the CE Lua plugin (JSON-RPC framing)
- Emit a JSONL audit log the CE plugin tails for the activity feed

Candidate languages: Python, Node/TypeScript, Go, Rust, C#.

## Decision

**Python 3.11+**, packaged with `uv` and shipped as `cegm-broker` on PyPI; users install via `uv tool install cegm-broker` (or `uvx cegm-broker` from the MCP client config).

## Consequences

### Positives

- **MCP SDK maturity.** The official `mcp` Python SDK (with FastMCP merged in-tree as `mcp.server.fastmcp`) is the canonical reference implementation. Decorator-based tool definitions, automatic JSON Schema from type hints, and built-in Streamable HTTP transport are all first-class. Equivalent quality is also available in TS, but Python wins on reference docs and example density.
- **OpenAI-compatible client ergonomics.** The `openai` Python SDK with `base_url=` redirected works out of the box against DeepSeek, Ollama, OpenRouter, vLLM, LM Studio, etc. — exactly the spread of providers our users will pick.
- **`uv` packaging story is clean on Windows.** `uv tool install` creates an isolated venv, tracks Python version, and is the same command path that MCP client configs reference (`"command": "uvx", "args": ["cegm-broker"]`). No global pip pollution.
- **Operator familiarity.** The intended user / contributor base for a CE plugin overlaps heavily with people who already have Python on hand. Lua + Python is a natural pairing in the modding community.
- **Logging / observability libraries** are mature; structured JSONL with `logging` + a custom formatter is ~30 lines.

### Negatives

- **Cold start cost.** Python interpreter startup is ~200ms; not a problem for a long-running broker but unpleasant if we ever flip to MCP stdio (which respawns per client). Mitigation: stay on HTTP transport.
- **Single-binary distribution is harder.** PyInstaller works on Windows but produces large binaries and triggers AV false-positives. Mitigation: don't use PyInstaller. Tell users to install `uv` (one curl-pipe, ~10 MB), then `uv tool install`.
- **Type checking is opt-in.** We adopt `mypy --strict` and CI gating from day one to keep refactors safe.

### Reversibility

The bridge protocol (JSON-RPC over a localhost TCP/Unix-domain socket) is language-agnostic. If Python ever becomes a problem we can swap the broker for Node or Go with no changes to the CE Lua side. The MCP server is also a portable concern.

## Alternatives considered

- **Node / TypeScript.** Tied for first on MCP SDK quality (`@modelcontextprotocol/sdk`) and arguably nicer for the Streamable HTTP transport. Rejected because Node's distribution story on Windows for non-developers is worse than `uv`-managed Python: no equivalent of `uv tool install` that handles runtime installation and isolation in one shot. `npx` works but mixes globally with the user's npm cache.
- **Go.** Excellent single-binary story (one `.exe`, no runtime). Rejected because the MCP Go SDK is younger and the OpenAI-compatible client landscape (we want streaming, tool calls, multiple provider quirks) is less mature. Reconsider if Phase 5 distribution friction becomes the dominant pain point.
- **Rust.** Same single-binary upside as Go. Rejected for the same SDK-maturity reason plus a steeper contribution barrier.
- **C# / .NET.** Native fit for Windows but adds a runtime dependency and a different ecosystem from where MCP and LLM tooling currently live. Rejected.
