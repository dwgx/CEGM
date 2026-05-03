# scripts/

Developer and end-user helper scripts.

## Planned

- `install.ps1` — Windows one-shot installer (Phase 5). Detects CE, copies the Lua plugin into `<CE>/autorun/CEGM/`, installs the broker via `uv tool install cegm-broker`, drops sample MCP client configs into `examples/`.
- `uninstall.ps1` — reverses `install.ps1`.
- `dev-bootstrap.sh` / `dev-bootstrap.ps1` — sets up the developer environment (creates `broker/.venv`, installs `[dev]` extras, links the plugin into a CE install for live editing).

## Status

Empty — placeholders only. See [docs/ROADMAP.md](../docs/ROADMAP.md) Phase 1 and Phase 5.
