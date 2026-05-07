"""Watchdog that exits the broker when its parent Cheat Engine process is gone.

The CE-side autorun script invokes ``cegm-broker --parent-pid <PID>``. We
poll that PID once per second and trigger uvicorn's graceful shutdown
(SIGINT) when it disappears. This keeps the broker's lifecycle pinned to
CE without complex job-object plumbing on Windows.
"""

from __future__ import annotations

import asyncio
import signal
from typing import Final

import psutil

from cegm_broker._logging import get_logger

_log = get_logger(__name__)
_POLL_INTERVAL_S: Final[float] = 1.0


async def watch(parent_pid: int) -> None:
    """Block until ``parent_pid`` exits, then ask the server to shut down."""
    _log.info("parent_watch.start", extra={"parent_pid": parent_pid})
    try:
        while True:
            try:
                alive = psutil.pid_exists(parent_pid)
            except (PermissionError, OSError, psutil.Error):
                _log.warning("parent_watch.pid_check_error", extra={"parent_pid": parent_pid})
                _request_shutdown()
                return
            if not alive:
                _log.info("parent_watch.parent_gone", extra={"parent_pid": parent_pid})
                _request_shutdown()
                return
            await asyncio.sleep(_POLL_INTERVAL_S)
    except asyncio.CancelledError:
        _log.info("parent_watch.cancelled")
        raise


def _request_shutdown() -> None:
    """Trigger uvicorn's graceful shutdown via SIGINT.

    ``signal.raise_signal`` is portable across Windows and POSIX in
    Python 3.8+; uvicorn's default signal handler converts it into a
    cooperative ``Server.should_exit`` flip.
    """
    signal.raise_signal(signal.SIGINT)
