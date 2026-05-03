"""Resolve filesystem paths CEGM uses at runtime.

All persistent state lives under ``%LOCALAPPDATA%\\CEGM\\`` on Windows. The
broker creates the directory tree lazily on first write. Tests can override
the root via the ``CEGM_DATA_DIR`` environment variable.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

_ENV_OVERRIDE: Final[str] = "CEGM_DATA_DIR"


def data_root() -> Path:
    """Return the base directory for all CEGM runtime state.

    On Windows this resolves to ``%LOCALAPPDATA%\\CEGM``. The directory may
    not exist yet — callers that write should use :func:`ensure_dir`.
    """
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "CEGM"
    # Sensible cross-platform fallback for development on macOS/Linux.
    return Path.home() / ".local" / "share" / "CEGM"


def config_path() -> Path:
    """Return the path to the user-editable JSON config file."""
    return data_root() / "config.json"


def logs_dir() -> Path:
    """Return the directory used for daily-rotated broker logs."""
    return data_root() / "logs"


def activity_dir() -> Path:
    """Return the directory used for per-session activity event logs."""
    return data_root() / "activity"


def snapshots_dir() -> Path:
    """Return the directory used for snapshot storage."""
    return data_root() / "snapshots"


def daily_log_file(when: datetime | None = None) -> Path:
    """Return the broker log file for the given UTC date (default: now)."""
    when = when or datetime.now(UTC)
    return logs_dir() / f"broker-{when:%Y%m%d}.jsonl"


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if missing; return it for chaining."""
    path.mkdir(parents=True, exist_ok=True)
    return path
