# scripts/

Developer and end-user helper scripts.

## Planned

- `install.ps1` — Windows one-shot installer (Phase 5). Detects CE, copies `plugin\*.lua` and `vendor\cheatengine-mcp-bridge\MCP_Server\ce_mcp_bridge.lua` into `<CE>\autorun\CEGM\`, installs the broker via `uv tool install cegm-broker`, drops a desktop shortcut to the dashboard.
- `uninstall.ps1` — reverses `install.ps1`.
- `dev-bootstrap.ps1` — sets up the developer environment: `uv sync` in `broker/`, symlinks plugin into a CE install for live editing, starts a watcher.
- `bump-vendor.ps1` — pulls the latest miscusi-peek commit, smoke-tests `tools/list`, updates the pinned reference in ADR-0004.

## Status

Empty — placeholders only. See [docs/ROADMAP.md](../docs/ROADMAP.md) Phase 1 and Phase 5.
