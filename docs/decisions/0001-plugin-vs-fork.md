# ADR-0001: Build CEGM as a Cheat Engine plugin, not a fork

- **Status:** accepted
- **Date:** 2026-05-03
- **Deciders:** dwgx (project owner)

## Context

CEGM needs to put an LLM in the loop with Cheat Engine's scanner. Two paths:

1. **Plugin** — Lua scripts loaded by stock Cheat Engine 7.5+ via its autorun folder. CE exposes a substantial Lua API (memory ops, scan engine, custom forms, socket I/O, JSON optional).
2. **Fork** — clone `cheat-engine/cheat-engine`, modify the Lazarus / FreePascal source, ship a rebranded binary with an LLM panel built into the GUI directly.

## Decision

**Plugin.** The MVP and any 0.x release ships as a Lua plugin plus an external Python broker. Forking is deferred indefinitely.

## Consequences

### Positives

- **No GPL distribution friction.** A Lua plugin loaded by CE doesn't redistribute CE. Users install upstream CE themselves; we distribute only our plugin (still GPL-2.0 to match) and the broker.
- **Tracks upstream automatically.** New CE releases just work. No merge conflicts with thousands of lines of Pascal we didn't write.
- **Tiny surface area.** Lua + Python instead of Lua + Python + FreePascal + Lazarus IDE workflow + Windows toolchain hell.
- **Faster MVP.** Estimated weeks, not months.
- **Lower barrier for contributors.** Lua and Python are accessible. FreePascal is not.

### Negatives

- **Cannot deeply restyle CE.** We can add docked panels and forms, but CE's chrome and main scanner UI stay as they are. The user accepts this — Phase 0 was explicit that "工具调用流水就行了" (tool-call activity feed is enough), so we don't need a fully redesigned UI.
- **Branding limits.** Users see "Cheat Engine" in the title bar; CEGM is the panel inside. Marketing-wise this is fine — CEGM is positioned as an add-on, not a replacement.
- **Lua main-thread constraint.** CE's Lua runs on the UI thread, so blocking calls freeze the GUI. Mitigated by pushing all heavy work (LLM I/O, MCP server, network) into the Python broker; the Lua side only does CE operations and short, non-blocking socket reads via `createTimer`.
- **Two processes to install.** Mitigated by an installer script in Phase 5.

### Reversibility

This decision is reversible. If CEGM grows enough to justify a fork (e.g. we want a fully bespoke UI, or upstream CE rejects API additions we'd want), we can layer a fork on top of an already-working plugin. The plugin's bridge protocol and tool surface are forwards-compatible with a fork that hosts them natively.

## Alternatives considered

- **External controller talking to CE via Lua RPC over the existing CE network protocol** — rejected. CE's network protocol is not designed as a public API and binds us to its quirks. A plugin runs in-process and uses the well-documented Lua bindings.
- **Standalone reimplementation of a memory editor + scanner** — rejected. CE represents 20 years of accumulated work on memory scanning, dissection, and Windows compatibility. Reimplementing is an enormous undertaking with no clear advantage for the LLM-driven use case.
