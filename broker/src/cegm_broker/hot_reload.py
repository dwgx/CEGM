"""Development hot-reload watcher for the web dashboard.

Monitors ``web/`` for file changes and publishes ``broker_reload`` events
so connected browser tabs refresh automatically. Polls mtimes every 1 s
— no external dependency needed.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path
from typing import Final

from cegm_broker._logging import get_logger
from cegm_broker.event_bus import Event, EventBus

_log = get_logger(__name__)

_POLL_INTERVAL: Final[float] = 1.0
_DEBOUNCE_S: Final[float] = 0.3  # coalesce rapid saves
_SKIP_SUFFIXES: Final[tuple[str, ...]] = (".tmp", "~", ".swp")


async def watch_web_dir(web_dir: Path, bus: EventBus) -> None:
    """Poll ``web_dir`` for changes; publish ``broker_reload`` on any delta.

    Runs forever until cancelled. Skips dotfiles and temp files.
    """
    _log.info("hot_reload.started", extra={"path": str(web_dir)})

    if not web_dir.is_dir():
        _log.warning("hot_reload.no_web_dir", extra={"path": str(web_dir)})
        return

    def _snapshot() -> dict[str, float]:
        snap: dict[str, float] = {}
        for root, _dirs, files in os.walk(web_dir):
            for f in files:
                if f.startswith(".") or f.endswith(_SKIP_SUFFIXES):
                    continue
                fp = os.path.join(root, f)
                with contextlib.suppress(OSError):
                    snap[fp] = os.path.getmtime(fp)
        return snap

    prev = _snapshot()

    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            curr = _snapshot()
        except OSError:
            continue

        changed = any(fp not in prev or prev[fp] != curr.get(fp) for fp in curr)
        changed = changed or any(fp not in curr for fp in prev)

        if changed:
            await asyncio.sleep(_DEBOUNCE_S)
            with contextlib.suppress(OSError):
                prev = _snapshot()
            _log.info("hot_reload.change_detected")
            with contextlib.suppress(Exception):
                await bus.publish(
                    Event.make(
                        "broker_reload",
                        {"ts": asyncio.get_event_loop().time()},
                    )
                )
        else:
            prev = curr
