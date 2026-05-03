"""Watchdog that exits the broker when its parent Cheat Engine process is gone.

The CE-side autorun script invokes ``cegm-broker --parent-pid <PID>``. We
poll that PID once per second and shut down gracefully when it disappears.
This keeps the broker's lifecycle pinned to CE without requiring complex
job-object plumbing on Windows.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from typing import Final

import psutil

from cegm_broker._logging import get_logger

_log = get_logger(__name__)
_POLL_INTERVAL_S: Final[float] = 1.0


async def watch(parent_pid: int) -> None:
    """Block until ``parent_pid`` exits, then trigger a graceful shutdown.

    Sends ``SIGTERM`` to ourselves on Windows (``signal.CTRL_BREAK_EVENT``
    isn't available without a console group) so uvicorn's lifespan hooks
    fire and the proxied child is closed cleanly.
    """
    _log.info("parent_watch.start", extra={"parent_pid": parent_pid})
    while True:
        if not psutil.pid_exists(parent_pid):
            _log.info("parent_watch.parent_gone", extra={"parent_pid": parent_pid})
            _request_shutdown()
            return
        await asyncio.sleep(_POLL_INTERVAL_S)


def _request_shutdown() -> None:
    """Tell the running event loop to begin a graceful exit."""
    if sys.platform == "win32":
        # On Windows ``signal.SIGTERM`` exists but is a no-op for asyncio
        # event-loop integration; raising it directly via ``os.kill`` does
        # not cooperatively trigger uvicorn's lifespan. Fallback: schedule
        # a sentinel exception.
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(loop.stop)
    else:  # pragma: no cover - non-Windows is best-effort
        os.kill(os.getpid(), signal.SIGTERM)
